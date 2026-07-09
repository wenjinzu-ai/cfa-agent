"""CFA-Agent LangGraph ReAct 闭环工作流定义

定义 think → act → observe → reflect → answer 的闭环工作流图
所有智能体共用此图结构，角色差异通过 think 节点的提示词实现

技术方案 §7.3：
- 基于 LangGraph StateGraph 构建
- 条件路由：think 输出决定下一步
- 循环终止：answer 或 max_steps
- 死循环检测：相同 tool_calls 重复出现
- 上下文溢出：压缩历史后继续或强制输出
- 实时流式：astream_run() 使用 astream(stream_mode=["updates","custom"]) 逐步推送
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Optional, TYPE_CHECKING

from langgraph.graph import END, StateGraph

from src.agents.config import AgentConfig
from src.llm.router import LLMRouter
from src.llm.token_counter import TokenCounter
from src.loop_engine.act_node import ActNode
from src.loop_engine.answer_node import AnswerNode
from src.loop_engine.observe_node import ObserveNode
from src.loop_engine.reflect_node import ReflectNode
from src.loop_engine.state import ReActState, StreamEvent, create_initial_state
from src.loop_engine.think_node import ThinkNode
from src.loop_engine.verify_node import VerifyNode
from src.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from src.agents.service import AgentService
    from src.guardrails.manager import GuardrailManager
    from src.memory.manager import MemoryManager
    from src.skills.registry import SkillRegistry

logger = logging.getLogger("cfa-agent.loop_engine.graph")


class ReActGraph:
    """ReAct 循环工作流图

    设计要点：
    - 基于 LangGraph StateGraph 构建
    - 所有 Agent 共用同一图结构
    - 行为差异完全由 AgentConfig 配置驱动
    - think 节点根据配置注入不同提示词
    - reflect 是内置节点，不是独立角色
    - 循环终止条件：answer 或 max_iterations

    Attributes:
        _think_node: 推理节点
        _act_node: 执行节点
        _observe_node: 观察节点
        _reflect_node: 反思节点
        _verify_node: 验证节点（自修正闭环）
        _answer_node: 回答节点
        _compiled_graph: 编译后的图（延迟构建）
    """

    def __init__(
        self,
        think_node: ThinkNode,
        act_node: ActNode,
        observe_node: ObserveNode,
        reflect_node: ReflectNode,
        verify_node: VerifyNode,
        answer_node: AnswerNode,
        guardrail_manager: Optional["GuardrailManager"] = None,
    ):
        self._think_node = think_node
        self._act_node = act_node
        self._observe_node = observe_node
        self._reflect_node = reflect_node
        self._verify_node = verify_node
        self._answer_node = answer_node
        self._guardrail_manager = guardrail_manager
        self._compiled_graph: Any = None

    @classmethod
    def create(
        cls,
        router: LLMRouter,
        tool_registry: ToolRegistry,
        token_counter: TokenCounter,
        agent_config: AgentConfig,
        guardrail_manager: Optional["GuardrailManager"] = None,
        memory: Optional["MemoryManager"] = None,
        skill_registry: Optional["SkillRegistry"] = None,
        agent_service: Optional["AgentService"] = None,
    ) -> ReActGraph:
        """工厂方法：从 AgentConfig 创建 ReActGraph

        Args:
            router: LLM 路由器
            tool_registry: 工具注册中心
            token_counter: Token 计数器
            agent_config: Agent 配置（包含所有行为参数）
            guardrail_manager: 护栏管理器
            memory: 记忆管理器（可选，启用后支持上下文记忆检索）
            skill_registry: 技能注册中心（可选，启用后支持技能触发）
            agent_service: Agent 服务（可选，入口 Agent 用于意图分类）

        Returns:
            ReActGraph: 配置好的工作流图
        """
        think_node = ThinkNode(
            router=router,
            tool_registry=tool_registry,
            token_counter=token_counter,
            enable_verify=agent_config.enable_verify,
            system_prompt=agent_config.system_prompt,
            think_prompt=agent_config.think_prompt,
            memory=memory,
            skill_registry=skill_registry,
            tool_names=agent_config.tools,
            agent_service=agent_service,
            is_entry_point=agent_config.is_entry_point,
        )

        act_node = ActNode(
            tool_registry=tool_registry,
            default_timeout=agent_config.default_timeout,
            tool_names=agent_config.tools,
        )

        observe_node = ObserveNode(
            token_counter=token_counter,
        )

        reflect_node = ReflectNode(
            router=router,
        )

        verify_node = VerifyNode(
            router=router,
            enable_verify=agent_config.enable_verify,
            max_verify_retries=agent_config.max_verify_retries,
        )

        answer_node = AnswerNode(
            router=router,
        )

        return cls(
            think_node=think_node,
            act_node=act_node,
            observe_node=observe_node,
            reflect_node=reflect_node,
            verify_node=verify_node,
            answer_node=answer_node,
            guardrail_manager=guardrail_manager,
        )

    def build(self) -> Any:
        """构建 ReAct 工作流图

        节点：
        - think: 推理决策
        - act: 执行工具
        - observe: 观察结果
        - reflect: 反思评估
        - verify: 结果验证（Supervisor 自修正闭环）
        - answer: 最终回答

        条件路由（从 think 出发）：
        - tool_calls 非空 → act
        - action_type == "ask_user" → observe（暂停等待用户）
        - action_type == "reflect" → reflect
        - action_type == "answer" → verify（先验证再回答）
        - 超出步数 → answer
        - 上下文溢出 → answer

        条件路由（从 verify 出发）：
        - verify_result.passed == True → answer
        - verify_result.passed == False → think（回到 think 重新委派）

        Returns:
            CompiledGraph: 编译后的 LangGraph 图
        """
        if self._compiled_graph is not None:
            return self._compiled_graph

        workflow = StateGraph(ReActState)

        workflow.add_node("think", self._think_node.execute)
        workflow.add_node("act", self._act_node.execute)
        workflow.add_node("observe", self._observe_node.execute)
        workflow.add_node("reflect", self._reflect_node.execute)
        workflow.add_node("verify", self._verify_node.execute)
        workflow.add_node("answer", self._answer_node.execute)

        workflow.set_entry_point("think")

        workflow.add_conditional_edges(
            "think",
            self._route_after_think,
            {
                "act": "act",
                "observe": "observe",
                "reflect": "reflect",
                "verify": "verify",
                "answer": "answer",
            },
        )

        workflow.add_edge("act", "observe")
        workflow.add_conditional_edges(
            "observe",
            self._route_after_observe,
            {
                "think": "think",
                "answer": "answer",
            },
        )
        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {
                "think": "think",
                "answer": "answer",
            },
        )
        workflow.add_conditional_edges(
            "verify",
            self._route_after_verify,
            {
                "think": "think",
                "answer": "answer",
            },
        )
        workflow.add_edge("answer", END)

        self._compiled_graph = workflow.compile()
        return self._compiled_graph

    @staticmethod
    def _route_after_think(state: ReActState) -> str:
        """think 节点后的条件路由

        路由规则：
        - pending_action.tool_calls 非空 → act
        - action_type == "ask_user" → observe
        - action_type == "reflect" → reflect
        - action_type == "answer" → verify（先验证再回答）
        - 超出步数 → answer
        - 上下文溢出 → answer

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        if state.get("context_overflow"):
            return "answer"

        if state["step_count"] >= state["max_steps"]:
            logger.warning(f"Max steps ({state['max_steps']}) reached")
            return "answer"

        action_type = state.get("action_type")
        pending_action = state.get("pending_action")

        if pending_action and pending_action.get("tool_calls"):
            return "act"

        if action_type == "ask_user":
            return "observe"

        if action_type == "reflect":
            reflect_count = state.get("consecutive_reflect_count", 0)
            if reflect_count >= 2:
                logger.warning("Max consecutive reflect count reached, forcing answer")
                return "answer"
            return "reflect"

        if action_type == "answer":
            if state.get("verify_count", 0) >= 2:
                return "answer"
            return "verify"

        return "answer"

    @staticmethod
    def _route_after_observe(state: ReActState) -> str:
        """observe 节点后的条件路由

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        if state.get("context_overflow"):
            return "answer"

        if state["step_count"] >= state["max_steps"]:
            return "answer"

        if state.get("consecutive_failures", 0) >= 3:
            return "answer"

        return "think"

    @staticmethod
    def _route_after_reflect(state: ReActState) -> str:
        """reflect 节点后的条件路由

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        if state.get("action_type") == "answer":
            return "answer"

        if state.get("escalate"):
            return "answer"

        return "think"

    @staticmethod
    def _route_after_verify(state: ReActState) -> str:
        """verify 节点后的条件路由

        验证通过 → answer  验证不通过 → think（重新委派）

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        verify_result = state.get("verify_result")
        if verify_result and verify_result.get("passed"):
            return "answer"

        if state.get("verify_count", 0) >= 2:
            return "answer"

        if state.get("context_overflow") or state["step_count"] >= state["max_steps"]:
            return "answer"

        return "think"

    async def run(self, task: str, context: Optional[dict] = None, max_steps: int = 20) -> ReActState:
        """运行 ReAct 循环

        Args:
            task: 任务描述
            context: 初始上下文
            max_steps: 最大步数

        Returns:
            ReActState: 最终状态
        """
        if self._guardrail_manager:
            input_result = await self._guardrail_manager.check_input(task)
            if not input_result.get("safe", True):
                logger.warning(f"Input blocked by guardrail: {input_result.get('reason')}")
                return {
                    **create_initial_state(task=task, context=context, max_steps=max_steps),
                    "final_answer": f"输入被安全护栏拦截: {input_result.get('reason', 'unknown')}",
                    "is_alerting": True,
                }

            self._guardrail_manager.start_behavior_session()

        graph = self.build()

        initial_state = create_initial_state(
            task=task,
            context=context,
            max_steps=max_steps,
        )

        logger.info(f"Starting ReAct loop for task: {task[:100]}")

        try:
            result = await graph.ainvoke(initial_state)
            logger.info(f"ReAct loop completed in {result.get('step_count', 0)} steps")

            if self._guardrail_manager and result.get("final_answer"):
                output_result = await self._guardrail_manager.check_output(result["final_answer"])
                if not output_result.get("safe", True):
                    filtered = output_result.get("filtered_output", result["final_answer"])
                    result["final_answer"] = filtered
                    logger.warning(f"Output filtered by guardrail: {output_result.get('reason')}")

            return result
        except Exception as e:
            logger.error(f"ReAct loop failed: {e}")
            initial_state["final_answer"] = f"抱歉，任务执行过程中出现错误: {str(e)}"
            initial_state["is_alerting"] = True
            return initial_state

    async def astream_run(
        self,
        task: str,
        context: Optional[dict] = None,
        max_steps: int = 20,
    ) -> AsyncGenerator[StreamEvent | dict, None]:
        """实时流式运行 ReAct 循环

        使用 LangGraph astream(stream_mode=["updates", "custom"]) 逐步推送事件：
        - updates: 每个节点执行后推送状态增量
        - custom: 节点内通过 stream_writer 推送自定义进度消息

        产出事件类型：
        - {"type": "thinking", "node": "think", "content": "...", "thought": "..."}
        - {"type": "tool_call", "node": "act", "tool_name": "...", "tool_args": {...}}
        - {"type": "tool_result", "node": "observe", "observation": "..."}
        - {"type": "reflect", "node": "reflect", "content": "..."}
        - {"type": "verify", "node": "verify", "content": "..."}
        - {"type": "answer", "node": "answer", "content": "...", "final_answer": "..."}
        - {"type": "state", ...}  (最终完整状态)

        Args:
            task: 任务描述
            context: 初始上下文
            max_steps: 最大步数

        Yields:
            StreamEvent | dict: 流式事件
        """
        if self._guardrail_manager:
            input_result = await self._guardrail_manager.check_input(task)
            if not input_result.get("safe", True):
                logger.warning(f"Input blocked by guardrail: {input_result.get('reason')}")
                yield StreamEvent(
                    type="error",
                    node="guardrail",
                    content=f"输入被安全护栏拦截: {input_result.get('reason', 'unknown')}",
                )
                return

            self._guardrail_manager.start_behavior_session()

        graph = self.build()

        initial_state = create_initial_state(
            task=task,
            context=context,
            max_steps=max_steps,
        )

        logger.info(f"Starting streaming ReAct loop for task: {task[:100]}")
        start_time = time.time()

        try:
            async for event in graph.astream(
                initial_state,
                stream_mode=["updates", "custom"],
            ):
                if isinstance(event, tuple) and len(event) == 2:
                    mode, data = event

                    if mode == "custom":
                        if isinstance(data, dict):
                            yield StreamEvent(**{k: v for k, v in data.items() if v is not None})
                    elif mode == "updates":
                        if isinstance(data, dict):
                            for node_name, state_update in data.items():
                                if node_name == "think":
                                    yield self._extract_think_event(state_update)
                                elif node_name == "act":
                                    yield self._extract_act_event(state_update)
                                elif node_name == "observe":
                                    yield self._extract_observe_event(state_update)
                                elif node_name == "reflect":
                                    yield self._extract_reflect_event(state_update)
                                elif node_name == "verify":
                                    yield self._extract_verify_event(state_update)
                                elif node_name == "answer":
                                    yield self._extract_answer_event(state_update)
                elif isinstance(event, dict):
                    event_type = event.get("type")
                    if event_type == "custom":
                        custom_data = event.get("data", {})
                        if isinstance(custom_data, dict):
                            yield StreamEvent(**custom_data)
                    elif event_type == "updates":
                        for node_name, state_update in event.items():
                            if node_name == "think":
                                yield self._extract_think_event(state_update)
                            elif node_name == "act":
                                yield self._extract_act_event(state_update)
                            elif node_name == "observe":
                                yield self._extract_observe_event(state_update)
                            elif node_name == "reflect":
                                yield self._extract_reflect_event(state_update)
                            elif node_name == "verify":
                                yield self._extract_verify_event(state_update)
                            elif node_name == "answer":
                                yield self._extract_answer_event(state_update)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Streaming ReAct loop completed in {duration_ms}ms")

        except Exception as e:
            logger.error(f"Streaming ReAct loop failed: {e}")
            yield StreamEvent(
                type="error",
                node="graph",
                content=f"任务执行出错: {str(e)}",
            )

    @staticmethod
    def _extract_think_event(update: dict) -> StreamEvent:
        pending = update.get("pending_action")
        if pending and pending.get("tool_calls"):
            first_tool = pending["tool_calls"][0] if pending["tool_calls"] else {}
            return StreamEvent(
                type="tool_call",
                node="think",
                content=update.get("current_thought", ""),
                thought=update.get("current_thought", ""),
                tool_name=first_tool.get("name", ""),
                tool_args=first_tool.get("args", {}),
            )
        return StreamEvent(
            type="thinking",
            node="think",
            content=update.get("current_thought", ""),
            thought=update.get("current_thought", ""),
        )

    @staticmethod
    def _extract_act_event(update: dict) -> StreamEvent:
        observation = update.get("last_observation", "")
        return StreamEvent(
            type="tool_result",
            node="act",
            observation=observation,
        )

    @staticmethod
    def _extract_observe_event(update: dict) -> StreamEvent:
        return StreamEvent(
            type="tool_result",
            node="observe",
            observation=update.get("last_observation", ""),
            step=update.get("step_count"),
        )

    @staticmethod
    def _extract_reflect_event(update: dict) -> StreamEvent:
        return StreamEvent(
            type="reflect",
            node="reflect",
            content=update.get("current_thought", ""),
        )

    @staticmethod
    def _extract_verify_event(update: dict) -> StreamEvent:
        verify_result = update.get("verify_result", {})
        passed = verify_result.get("passed", True) if verify_result else True
        return StreamEvent(
            type="verify",
            node="verify",
            content=f"验证{'通过' if passed else '不通过'}",
        )

    @staticmethod
    def _extract_answer_event(update: dict) -> StreamEvent:
        return StreamEvent(
            type="answer",
            node="answer",
            content=update.get("final_answer", ""),
        )