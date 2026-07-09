"""CFA-Agent 意图分类器

独立的 LLM 意图分类调用，与 think 节点解耦。
在 Supervisor 的 think 流程之前，先调用一次大模型做结构化意图分析，
将分析结果注入 think 的上下文，引导 Supervisor 做出更准确的路由决策。

工作原理：
1. 从 AgentService 动态读取每个 Agent 的 capabilities 声明
2. 构建意图分类的 system + user 消息（无硬编码路由规则）
3. 调用 LLM 获取结构化意图标签（domain/action_type/complexity/...）
4. 将意图标签注入 Supervisor 的 think 上下文
5. Supervisor 根据意图标签做路由决策

新增 Agent 时：只需在 agents.yaml 中添加 capabilities 字段，
意图分类器自动感知，零代码改动。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.service import AgentService
    from src.llm.router import LLMRouter

logger = logging.getLogger("cfa-agent.loop_engine.intent_classifier")

INTENT_SYSTEM_PROMPT = """\
你是一个意图分类器。你的唯一任务是分析用户输入，输出结构化的意图标签。
不要回答用户的问题，不要执行任何操作，只输出意图分析 JSON。

可用的专家智能体及其能力：

{agent_capabilities}

路由原则：
- 根据用户输入的任务需求，匹配能力最合适的专家
- 如果任务需要某个专家独有的能力（如编码、任务分解、审查），优先选择该专家
- 如果任务只需要搜索和简单处理，选择通用的执行者
- 如果是闲聊问候，suggested_agent 设为 "none"
- 如果不确定，选择能力覆盖面最匹配的专家\
"""

INTENT_USER_TEMPLATE = """\
分析以下用户输入的意图：

用户输入：{task}

请输出 JSON 格式的意图标签，包含以下字段：
- domain: 领域（finance/tech/general/code/data/...）
- action_type: 动作类型（search/analysis/coding/planning/review/chat/...）
- complexity: 复杂度（simple/medium/complex）
- needs_realtime_data: 是否需要实时数据（true/false）
- needs_coding: 是否需要写代码（true/false）
- suggested_agent: 推荐委派目标（agent_id，闲聊设为 "none"）\
"""


class IntentClassifier:
    """意图分类器

    职责：
    - 从 AgentService 动态读取 capabilities 生成能力描述
    - 构建意图分类的 LLM 消息（无硬编码路由规则）
    - 调用 LLM 获取结构化意图标签
    - 解析 LLM 响应为意图字典

    独立于 think 节点，单独调用大模型。
    新增 Agent 时自动感知，零代码改动。
    """

    def __init__(
        self,
        agent_service: Optional["AgentService"] = None,
        router: Optional["LLMRouter"] = None,
    ):
        self._agent_service = agent_service
        self._router = router
        self._capabilities_cache: Optional[str] = None

    async def classify(self, task: str) -> Optional[dict]:
        """对用户输入做意图分类

        独立调用一次大模型，返回结构化意图标签。

        Args:
            task: 用户输入文本

        Returns:
            意图字典，或 None（分类失败时）
        """
        if not self._router:
            logger.warning("IntentClassifier has no router, skipping classification")
            return None

        capabilities = self._build_agent_capabilities()
        system_msg = INTENT_SYSTEM_PROMPT.format(agent_capabilities=capabilities)
        user_msg = INTENT_USER_TEMPLATE.format(task=task)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        try:
            response = await self._router.route_classify(messages)
            content = response.get("content", "")
            intent = self._parse_intent(content)
            if intent:
                logger.info("Intent classified: %s", intent)
            else:
                logger.warning("Failed to parse intent from LLM response: %s", content[:200])
            return intent
        except Exception as e:
            logger.error("Intent classification LLM call failed: %s", e)
            return None

    def _parse_intent(self, text: str) -> Optional[dict]:
        """从 LLM 响应中解析意图标签

        支持以下格式：
        - 纯 JSON 对象
        - ```json ... ``` 代码块
        - 内联 JSON 对象（包含 domain 或 suggested_agent 字段）

        Args:
            text: LLM 响应文本

        Returns:
            解析后的意图字典，或 None
        """
        if not text:
            return None

        def _try_parse(t: str) -> Optional[dict]:
            try:
                data = json.loads(t)
                if isinstance(data, dict) and ("domain" in data or "suggested_agent" in data or "action_type" in data):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
            return None

        parsed = _try_parse(text.strip())
        if parsed:
            return parsed

        code_blocks = re.findall(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        for block in code_blocks:
            parsed = _try_parse(block.strip())
            if parsed:
                return parsed

        inline_match = re.search(r'\{[^{}]*"(?:domain|suggested_agent|action_type)"[^{}]*\}', text)
        if inline_match:
            parsed = _try_parse(inline_match.group(0))
            if parsed:
                return parsed

        return None

    def format_intent_for_context(self, intent: Optional[dict]) -> str:
        """将意图标签格式化为可注入 think 上下文的文本

        Args:
            intent: 意图字典

        Returns:
            str: 格式化的意图描述文本
        """
        if not intent:
            return ""

        lines = ["📋 意图分析结果："]
        field_labels = {
            "domain": "领域",
            "action_type": "动作类型",
            "complexity": "复杂度",
            "needs_realtime_data": "需要实时数据",
            "needs_coding": "需要编码",
            "suggested_agent": "推荐专家",
        }
        for key, label in field_labels.items():
            value = intent.get(key)
            if value is not None:
                lines.append(f"  - {label}：{value}")

        suggested = intent.get("suggested_agent")
        if suggested and suggested != "none":
            agent_name = self._get_agent_display_name(suggested)
            lines.append(f"\n→ 建议委派给 {agent_name}")

        return "\n".join(lines)

    def _get_agent_display_name(self, agent_id: str) -> str:
        """获取 Agent 的可读显示名称"""
        if self._agent_service:
            config = self._agent_service.get(agent_id)
            if config:
                return f"{config.name}（{agent_id}）"
        return agent_id

    def _build_agent_capabilities(self) -> str:
        """从 AgentService 动态生成 Agent 能力描述

        优先使用 capabilities 字段（结构化能力声明），
        降级使用 tools 列表（工具级描述）。

        Returns:
            str: 格式化的 Agent 能力描述
        """
        if self._capabilities_cache:
            return self._capabilities_cache

        if not self._agent_service:
            return self._default_capabilities()

        agents = self._agent_service.list_all()
        if not agents:
            return self._default_capabilities()

        lines = []
        for agent in agents:
            if agent.is_entry_point:
                continue
            if agent.capabilities:
                lines.append(f"- {agent.id}（{agent.name}）：")
                for cap in agent.capabilities:
                    lines.append(f"  · {cap}")
            else:
                tools_str = ", ".join(agent.tools) if agent.tools else "无"
                lines.append(f"- {agent.id}（{agent.name}）：工具=[{tools_str}]")

        if not lines:
            return self._default_capabilities()

        self._capabilities_cache = "\n".join(lines)
        return self._capabilities_cache

    @staticmethod
    def _default_capabilities() -> str:
        """默认 Agent 能力描述（AgentService 不可用时的降级方案）"""
        return (
            "- planner（规划者）：\n"
            "  · 任务分解和策略制定\n"
            "  · 识别子任务依赖关系\n"
            "  · 生成执行计划\n"
            "- executor（执行者）：\n"
            "  · 信息检索和搜索\n"
            "  · 文本处理和摘要\n"
            "  · 数据分析和统计\n"
            "  · API 调用\n"
            "  · 文件读写\n"
            "  · 简单计算和格式转换\n"
            "- code_agent（编码专家）：\n"
            "  · 编写和执行 Python 代码\n"
            "  · 网页数据抓取和爬虫\n"
            "  · 数据库查询和操作\n"
            "  · 脚本调试和错误修复\n"
            "  · 数据处理和转换\n"
            "- reviewer（审查者）：\n"
            "  · 结果校验和质量审查\n"
            "  · 事实核查\n"
            "  · 代码审查"
        )

    def invalidate_cache(self) -> None:
        """清除能力描述缓存（Agent 配置变更时调用）"""
        self._capabilities_cache = None