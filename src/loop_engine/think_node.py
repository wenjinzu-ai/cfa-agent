"""CFA-Agent 推理节点

think 节点：LLM 决策工具调用 or 回答
不同 Agent 的 think 侧重由 system_prompt 和 think_prompt 配置决定

技术方案 §7.5.1：
1. 上下文注入：读取 context 字段
2. 记忆检索：从 MemoryManager 获取相关历史经验
3. Skills 触发：从 SkillRegistry 匹配触发词，注入专业提示词
4. 工具过滤：只暴露 agent_config.tools 中指定的工具，实现权限控制
5. LLM 推理：LLM 原生返回 tool_calls 或 content
6. 路由决策：根据 LLM 返回判断路由方向
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional, TYPE_CHECKING

from src.llm.router import LLMRouter
from src.llm.token_counter import TokenCounter
from src.loop_engine.intent_classifier import IntentClassifier
from src.loop_engine.state import ReActState
from src.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from src.agents.service import AgentService
    from src.memory.manager import MemoryManager
    from src.skills.registry import SkillRegistry

logger = logging.getLogger("cfa-agent.loop_engine.think")


class ThinkNode:
    """推理节点

    职责：
    - 调用 LLM 进行推理决策
    - 决定下一步是调用工具还是直接回答
    - 通过 bind_tools 将工具列表传给 LLM，原生返回 tool_calls
    - 检测死循环（相同 tool_calls 重复出现）
    - 从记忆系统检索相关历史经验注入 prompt
    - 从 Skills 系统匹配触发词，注入专业提示词（Phase 4）
    - 工具过滤：只暴露 Agent 配置中指定的工具给 LLM

    Attributes:
        _router: LLM 路由器
        _tool_registry: 工具注册中心
        _token_counter: Token 计数器
        _memory: 记忆管理器（Phase 3 对接）
        _skill_registry: 技能注册表（Phase 4 对接）
        _enable_verify: 是否启用验证（用于 think 节点感知）
        _system_prompt: 系统提示词
        _think_prompt: think 节点提示词模板
        _tool_names: Agent 允许使用的工具名称列表（空列表 = 允许所有）
    """

    def __init__(
        self,
        router: LLMRouter,
        tool_registry: ToolRegistry,
        token_counter: TokenCounter,
        enable_verify: bool = False,
        system_prompt: str = "",
        think_prompt: str = "",
        memory: Optional["MemoryManager"] = None,
        skill_registry: Optional["SkillRegistry"] = None,
        tool_names: Optional[list[str]] = None,
        agent_service: Optional["AgentService"] = None,
        is_entry_point: bool = False,
    ):
        self._router = router
        self._tool_registry = tool_registry
        self._token_counter = token_counter
        self._enable_verify = enable_verify
        self._system_prompt = system_prompt or self._default_system_prompt()
        self._think_prompt = think_prompt or self._default_think_prompt()
        self._memory = memory
        self._skill_registry = skill_registry
        self._tool_names: list[str] = tool_names if tool_names is not None else []
        self._is_entry_point = is_entry_point
        self._intent_classifier: Optional[IntentClassifier] = None
        if is_entry_point and agent_service and router:
            self._intent_classifier = IntentClassifier(agent_service, router)

    async def _search_memories(self, task: str, current_thought: str) -> str:
        """检索相关记忆

        Phase 3：对接真实记忆系统
        Phase 2 兼容：无 MemoryManager 时返回桩文本

        Args:
            task: 当前任务描述
            current_thought: 当前推理内容

        Returns:
            str: 格式化的记忆文本
        """
        if self._memory is None:
            return "(Phase 3: 记忆检索桩实现，暂无相关记忆)"

        try:
            return await self._memory.search_for_think(task, current_thought)
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
            return "(记忆检索失败，继续执行)"

    def _build_dynamic_agent_list(self) -> str:
        """动态生成专家团队描述（仅 Supervisor 使用）

        从 AgentService 的 build_agent_list_description 方法获取，
        替代 Supervisor system_prompt 中的硬编码专家列表。
        新增 Agent 时自动感知，无需修改提示词。

        Returns:
            str: 格式化的专家团队描述
        """
        if not self._intent_classifier or not self._intent_classifier._agent_service:
            return ""
        return self._intent_classifier._agent_service.build_agent_list_description()

    def _get_triggered_skills(self, task: str) -> list[dict]:
        """获取触发的技能

        Phase 4：从 SkillRegistry 匹配触发词

        Args:
            task: 当前任务描述

        Returns:
            list[dict]: 触发的技能列表
        """
        if self._skill_registry is None:
            return []

        try:
            triggered = self._skill_registry.get_triggered_skills(task)
            if triggered:
                logger.info(f"Triggered skills: {[s['name'] for s in triggered]}")
            return triggered
        except Exception as e:
            logger.warning(f"Skill trigger failed: {e}")
            return []

    def _build_skill_prompt(self, triggered_skills: list[dict]) -> str:
        """构建技能提示词（渐进式披露）

        第1层：所有技能的 name + description 始终注入（~100 tokens）
        第2层：被触发的技能完整 prompt 按需注入

        Args:
            triggered_skills: 触发的技能列表

        Returns:
            str: 合并后的技能提示词
        """
        if self._skill_registry is None:
            return ""

        all_skills = self._skill_registry.list_all()
        if not all_skills:
            return ""

        parts = []

        catalog_lines = ["Available skills (auto-loaded when relevant):"]
        for skill in all_skills:
            catalog_lines.append(f"- {skill['name']}: {skill.get('description', '')}")
        parts.append("\n".join(catalog_lines))

        if triggered_skills:
            parts.append("\nTriggered skills for this task:")
            for skill in triggered_skills:
                name = skill.get("name", "unknown")
                prompt = skill.get("prompt", "")
                if prompt:
                    parts.append(f"\n=== {name} Skill ===\n{prompt}\n")

        return "\n\n".join(parts)

    def _default_system_prompt(self) -> str:
        """默认系统提示词"""
        return (
            "You are an AI assistant that can use tools to complete tasks.\n"
            "Follow the ReAct pattern: think about what to do, use tools when needed, "
            "observe results, and provide a final answer when you have enough information.\n\n"
            "Rules:\n"
            "- Do NOT repeat the same tool call with the same parameters\n"
            "- If you have enough information, provide your final answer directly\n"
            "- If you need information that tools cannot provide, ask the user\n"
            "- If you detect you are stuck, reflect on your approach"
        )

    def _default_think_prompt(self) -> str:
        """默认 think 提示词模板"""
        return (
            "Current task: {task}\n\n"
            "Context:\n{context}\n\n"
            "Relevant memories:\n{memories}\n\n"
            "Previous steps:\n{history}\n\n"
            "Reflect result (if any):\n{reflect_result}\n\n"
            "Step {step_count}/{max_steps}\n\n"
            "Analyze the situation and decide what to do next. "
            "If you need to use a tool, select it. "
            "If you have enough information, provide your final answer. "
            "If you need to reflect on your approach, say so."
        )

    async def execute(self, state: ReActState) -> dict:
        """执行推理

        流程：
        0. 意图分类（仅入口 Agent，独立 LLM 调用）
        1. 上下文注入
        2. 记忆检索（Phase 3 对接真实记忆系统）
        3. Skills 触发（Phase 4 对接技能系统）
        4. 工具绑定
        5. LLM 推理
        6. 路由决策

        Args:
            state: 当前 ReAct 状态

        Returns:
            dict: 状态更新
        """
        logger.info(f"Think node executing, step {state['step_count'] + 1}/{state['max_steps']}")

        intent_update = {}
        if self._is_entry_point and self._intent_classifier and not state.get("intent"):
            logger.info("Running intent classification before think")
            intent = await self._intent_classifier.classify(state["task"])
            if intent:
                intent_update = {"intent": intent}
                logger.info("Intent classified: %s", intent)

        current_thought = state.get("current_thought", "")
        memories_text = await self._search_memories(state["task"], current_thought)
        triggered_skills = self._get_triggered_skills(state["task"])
        skill_prompt = self._build_skill_prompt(triggered_skills)

        messages = self._build_messages(state, memories_text, skill_prompt)

        tools = self._get_tools_schema()

        if self._token_counter.is_overflow(messages):
            logger.warning("Context window overflow detected, compressing history")
            return {
                "context_overflow": True,
                "action_type": "answer",
                "current_thought": "上下文窗口溢出，基于已有信息输出答案",
                **intent_update,
            }

        try:
            response = await self._router.route_think(
                messages=messages,
                tools=tools if tools else None,
            )
        except Exception as e:
            logger.error(f"LLM call failed in think node: {e}")
            return {
                "action_type": "answer",
                "current_thought": f"LLM 调用失败: {str(e)}",
                "final_answer": f"抱歉，推理过程中出现错误: {str(e)}",
                "is_alerting": True,
                **intent_update,
            }

        result = self._process_llm_response(response, state)
        if intent_update and "intent" not in result:
            result.update(intent_update)
        return result

    def _build_messages(self, state: ReActState, memories_text: str = "", skill_prompt: str = "") -> list[dict]:
        """构建 LLM 消息列表

        Args:
            state: 当前状态
            memories_text: 检索到的记忆文本
            skill_prompt: 触发的技能提示词（Phase 4）

        Returns:
            list[dict]: OpenAI 格式消息列表
        """
        history_text = self._format_history(state["history"])
        context_data = state.get("context", {})
        context_text = self._format_context(context_data)
        reflect_text = self._format_reflect_result(state.get("reflect_result"))
        conversation_history = context_data.get("conversation_history", [])

        think_content = self._think_prompt.format(
            task=state["task"],
            context=context_text,
            memories=memories_text or "(暂无相关历史经验)",
            history=history_text,
            reflect_result=reflect_text,
            tools=self._format_tools(self._get_tools_schema()),
            step_count=state["step_count"],
            max_steps=state["max_steps"],
        )

        system_content = self._system_prompt
        if skill_prompt:
            system_content = self._system_prompt + "\n\n" + skill_prompt

        if self._is_entry_point and self._intent_classifier:
            intent = state.get("intent")
            intent_text = self._intent_classifier.format_intent_for_context(intent)
            if intent_text:
                system_content = system_content + "\n\n" + intent_text

            agent_list_text = self._build_dynamic_agent_list()
            if agent_list_text:
                system_content = system_content + "\n\n" + agent_list_text

        messages = [
            {"role": "system", "content": system_content},
        ]

        for msg in conversation_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content})

        messages.append({"role": "user", "content": think_content})

        for step in state["history"]:
            if step.get("thought"):
                messages.append({"role": "assistant", "content": step["thought"]})
            if step.get("observation"):
                messages.append({"role": "user", "content": f"Observation: {step['observation']}"})

        return messages

    def _get_tools_schema(self) -> list[dict]:
        """获取工具的 OpenAI Function Calling Schema

        按 Agent 配置的 tool_names 过滤，只暴露 Agent 有权使用的工具。
        空列表表示允许所有已注册工具。

        Returns:
            list[dict]: 工具 Schema 列表
        """
        try:
            schemas = self._tool_registry.get_openai_schemas()
        except Exception:
            return []

        if not self._tool_names:
            return schemas

        filtered = [s for s in schemas if s.get("function", {}).get("name") in self._tool_names]
        logger.debug(
            "Tool filtering: %d/%d tools exposed (%s)",
            len(filtered), len(schemas),
            ", ".join(self._tool_names),
        )
        return filtered

    def _process_llm_response(self, response: dict, state: ReActState) -> dict:
        """处理 LLM 响应，决定路由方向

        Args:
            response: LLM 响应
            state: 当前状态

        Returns:
            dict: 状态更新
        """
        tool_calls = response.get("tool_calls", [])
        content = response.get("content", "")

        if not tool_calls:
            tool_calls = self._extract_tool_calls_from_text(content)

        if tool_calls:
            if self._is_dead_loop(tool_calls, state):
                logger.warning("Dead loop detected: same tool_calls repeated")
                return {
                    "action_type": "reflect",
                    "current_thought": "检测到死循环：重复调用相同工具，需要反思调整策略",
                    "pending_action": {"tool_calls": tool_calls},
                }

            return {
                "pending_action": {"tool_calls": tool_calls},
                "action_type": None,
                "current_thought": content or f"选择调用 {len(tool_calls)} 个工具",
            }

        if self._is_ask_user(content):
            question = self._extract_question(content)
            return {
                "action_type": "ask_user",
                "user_question": question,
                "current_thought": f"需要向用户提问: {question}",
            }

        if self._should_reflect(content, state):
            return {
                "action_type": "reflect",
                "current_thought": content,
            }

        return {
            "action_type": "answer",
            "current_thought": content,
            "final_answer": content,
        }

    def _extract_tool_calls_from_text(self, content: str) -> list[dict]:
        """从 LLM 文本输出中提取工具调用

        当 LLM 不支持原生 Function Calling 时，会在文本中输出 JSON 格式的工具调用。
        支持以下格式：
        - ```json\n{"tool_name": "xxx", "parameters": {...}}\n```
        - {"tool_name": "xxx", "parameters": {...}}
        - {"name": "xxx", "arguments": {...}}
        - [{"tool_name": "xxx", ...}, ...]

        Args:
            content: LLM 返回的文本内容

        Returns:
            list[dict]: 提取的 tool_calls 列表（标准格式）
        """
        if not content:
            return []

        tool_calls = []

        code_blocks = re.findall(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
        for block in code_blocks:
            calls = self._parse_json_tool_calls(block.strip())
            tool_calls.extend(calls)

        if not tool_calls:
            inline_blocks = re.findall(r'\{[\s\S]*?"(?:tool_name|name)"[\s\S]*?\}', content)
            for block in inline_blocks:
                calls = self._parse_json_tool_calls(block)
                tool_calls.extend(calls)

        if tool_calls:
            logger.info(f"Extracted {len(tool_calls)} tool calls from text output")

        return tool_calls

    @staticmethod
    def _parse_json_tool_calls(text: str) -> list[dict]:
        """解析 JSON 格式的工具调用

        Args:
            text: JSON 文本

        Returns:
            list[dict]: 标准格式的 tool_calls
        """
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if isinstance(parsed, dict):
            name = parsed.get("tool_name") or parsed.get("name", "")
            args = parsed.get("parameters") or parsed.get("arguments") or parsed.get("args", {})
            if name and isinstance(args, dict):
                return [{"id": "tc_0", "name": name, "args": args}]
        elif isinstance(parsed, list):
            results = []
            for i, item in enumerate(parsed):
                if isinstance(item, dict):
                    name = item.get("tool_name") or item.get("name", "")
                    args = item.get("parameters") or item.get("arguments") or item.get("args", {})
                    if name and isinstance(args, dict):
                        results.append({"id": f"tc_{i}", "name": name, "args": args})
            return results

        return []

    def _is_dead_loop(self, tool_calls: list[dict], state: ReActState) -> bool:
        """检测死循环

        检查最近 3 步是否有相同的 tool_calls（name + args 相同）

        Args:
            tool_calls: 当前 tool_calls
            state: 当前状态

        Returns:
            bool: 是否检测到死循环
        """
        current_signatures = set()
        for tc in tool_calls:
            sig = f"{tc.get('name', '')}:{json.dumps(tc.get('args', {}), sort_keys=True)}"
            current_signatures.add(sig)

        repeat_count = 0
        for step in reversed(state["history"][-3:]):
            action = step.get("action")
            if not action:
                continue
            past_calls = action.get("tool_calls", [])
            past_signatures = set()
            for tc in past_calls:
                sig = f"{tc.get('name', '')}:{json.dumps(tc.get('args', {}), sort_keys=True)}"
                past_signatures.add(sig)
            if current_signatures == past_signatures:
                repeat_count += 1

        return repeat_count >= 2

    def _is_ask_user(self, content: str) -> bool:
        """判断是否需要向用户提问

        Args:
            content: LLM 返回的文本内容

        Returns:
            bool: 是否需要反问用户
        """
        if not content:
            return False
        ask_patterns = [
            r"ask_user",
            r"需要.*信息",
            r"请提供",
            r"请问",
            r"需要确认",
            r"cannot proceed without",
            r"need more information",
        ]
        content_lower = content.lower()
        for pattern in ask_patterns:
            if re.search(pattern, content_lower):
                return True
        return False

    def _extract_question(self, content: str) -> str:
        """从 LLM 回复中提取向用户的问题

        Args:
            content: LLM 返回内容

        Returns:
            str: 提取的问题
        """
        question = content
        for prefix in ["ask_user:", "ask_user：", "问题：", "question:"]:
            if prefix in content.lower():
                idx = content.lower().find(prefix)
                question = content[idx + len(prefix):].strip()
                break
        return question[:500] if len(question) > 500 else question

    def _should_reflect(self, content: str, state: ReActState) -> bool:
        """判断是否需要反思

        Args:
            content: LLM 返回内容
            state: 当前状态

        Returns:
            bool: 是否需要反思
        """
        if state.get("consecutive_reflect_count", 0) >= 2:
            return False

        reflect_keywords = [
            "reflect", "反思", "重新考虑", "换一个思路",
            "approach is not working", "stuck", "need to reconsider",
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in reflect_keywords)

    @staticmethod
    def _format_tools(tools_schema: list[dict]) -> str:
        """格式化工具Schema为文本"""
        if not tools_schema:
            return "(无可用工具，直接回答)"
        parts = []
        for t in tools_schema:
            fn = t.get("function", {})
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            parts.append(f"- {name}: {desc}")
            if params.get("properties"):
                for pname, pinfo in params["properties"].items():
                    parts.append(f"  * {pname} ({pinfo.get('type', 'any')})")
        return "\n".join(parts)

    @staticmethod
    def _format_history(history: list) -> str:
        """格式化历史步骤"""
        if not history:
            return "(无历史步骤)"
        parts = []
        for i, step in enumerate(history[-5:]):
            thought = step.get("thought", "")
            action = step.get("action", "")
            obs = step.get("observation", "")
            parts.append(f"Step {i + 1}:")
            if thought:
                parts.append(f"  Thought: {thought[:200]}")
            if action:
                parts.append(f"  Action: {json.dumps(action, ensure_ascii=False)[:200]}")
            if obs:
                parts.append(f"  Observation: {obs[:200]}")
        return "\n".join(parts)

    @staticmethod
    def _format_context(context: dict) -> str:
        """格式化上下文"""
        if not context:
            return "(无额外上下文)"
        return json.dumps(context, ensure_ascii=False, indent=2)[:1000]

    @staticmethod
    def _format_reflect_result(reflect_result: Optional[dict]) -> str:
        """格式化反思结果"""
        if not reflect_result:
            return "(无反思结果)"
        return json.dumps(reflect_result, ensure_ascii=False, indent=2)[:500]