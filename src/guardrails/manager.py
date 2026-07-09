"""CFA-Agent 护栏管理器

统一协调所有护栏组件，提供全链路安全检查
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.guardrails.input_guard import InputGuard
from src.guardrails.output_guard import OutputGuard
from src.guardrails.behavior_guard import BehaviorGuard
from src.guardrails.tool_guard import ToolGuard
from src.guardrails.security import SecurityPolicy

logger = logging.getLogger("cfa-agent.guardrails.manager")


class GuardrailManager:
    """护栏管理器

    职责：
    - 统一协调所有护栏组件
    - 提供全链路安全检查
    - 管理护栏配置
    - 汇总安全报告
    """

    def __init__(
        self,
        input_guard: Optional[InputGuard] = None,
        output_guard: Optional[OutputGuard] = None,
        behavior_guard: Optional[BehaviorGuard] = None,
        tool_guard: Optional[ToolGuard] = None,
        security: Optional[SecurityPolicy] = None,
        enabled: bool = True,
    ):
        self._input_guard = input_guard or InputGuard()
        self._output_guard = output_guard or OutputGuard()
        self._behavior_guard = behavior_guard or BehaviorGuard()
        self._tool_guard = tool_guard or ToolGuard()
        self._security = security or SecurityPolicy()
        self._enabled = enabled

    @property
    def input_guard(self) -> InputGuard:
        return self._input_guard

    @property
    def output_guard(self) -> OutputGuard:
        return self._output_guard

    @property
    def behavior_guard(self) -> BehaviorGuard:
        return self._behavior_guard

    @property
    def tool_guard(self) -> ToolGuard:
        return self._tool_guard

    @property
    def security(self) -> SecurityPolicy:
        return self._security

    async def check_input(self, user_input: str) -> dict:
        """检查输入安全性

        Args:
            user_input: 用户输入

        Returns:
            dict: 输入检查结果
        """
        if not self._enabled:
            return {"safe": True, "reason": None, "filtered_input": user_input}

        result = await self._input_guard.check(user_input)

        await self._security.audit(
            action="input_check",
            agent_id="system",
            details={
                "safe": result["safe"],
                "risk_level": result.get("risk_level", "unknown"),
            },
        )

        return result

    async def check_output(self, output: str) -> dict:
        """检查输出安全性

        Args:
            output: 输出文本

        Returns:
            dict: 输出检查结果
        """
        if not self._enabled:
            return {"safe": True, "reason": None, "filtered_output": output}

        result = await self._output_guard.check(output)

        await self._security.audit(
            action="output_check",
            agent_id="system",
            details={
                "safe": result["safe"],
                "has_sensitive": result.get("has_sensitive_data", False),
                "has_inappropriate": result.get("has_inappropriate_content", False),
            },
        )

        return result

    async def check_behavior(
        self,
        current_step: int,
        used_tokens: int,
        deviation_score: float = 0.0,
        consecutive_deviation_count: int = 0,
        consecutive_failures: int = 0,
        action_signature: str = "",
    ) -> dict:
        """检查行为合规性

        Args:
            current_step: 当前步数
            used_tokens: 已使用 Token 数
            deviation_score: 偏差分数
            consecutive_deviation_count: 连续偏差次数
            consecutive_failures: 连续失败次数
            action_signature: 动作签名

        Returns:
            dict: 行为检查结果
        """
        if not self._enabled:
            return {"allowed": True, "reasons": [], "should_reflect": False}

        return await self._behavior_guard.full_check(
            current_step=current_step,
            used_tokens=used_tokens,
            deviation_score=deviation_score,
            consecutive_deviation_count=consecutive_deviation_count,
            consecutive_failures=consecutive_failures,
            action_signature=action_signature,
        )

    async def check_tool_call(
        self,
        tool_name: str,
        agent_id: str,
        args: dict,
        schema: Optional[dict] = None,
    ) -> dict:
        """检查工具调用安全性

        Args:
            tool_name: 工具名称
            agent_id: 智能体 ID
            args: 工具参数
            schema: 参数 Schema

        Returns:
            dict: 工具调用检查结果
        """
        if not self._enabled:
            return {"allowed": True, "reasons": [], "requires_approval": False}

        result = await self._tool_guard.full_check(tool_name, agent_id, args, schema)

        await self._security.audit(
            action="tool_call_check",
            agent_id=agent_id,
            details={
                "tool_name": tool_name,
                "allowed": result["allowed"],
                "requires_approval": result.get("requires_approval", False),
            },
        )

        return result

    async def full_pipeline_check(
        self,
        user_input: str,
        agent_id: str,
        current_step: int = 0,
        used_tokens: int = 0,
    ) -> dict:
        """执行全链路安全检查

        Args:
            user_input: 用户输入
            agent_id: 智能体 ID
            current_step: 当前步数
            used_tokens: 已使用 Token 数

        Returns:
            dict: 全链路检查结果
        """
        input_result = await self.check_input(user_input)
        behavior_result = await self.check_behavior(
            current_step=current_step,
            used_tokens=used_tokens,
        )

        safe = input_result.get("safe", True) and behavior_result.get("allowed", True)
        reasons = []
        if not input_result.get("safe", True):
            reasons.append(f"输入检查: {input_result.get('reason', 'unknown')}")
        if not behavior_result.get("allowed", True):
            reasons.extend(behavior_result.get("reasons", []))

        return {
            "safe": safe,
            "reasons": reasons,
            "input_check": input_result,
            "behavior_check": behavior_result,
        }

    def get_security_report(self) -> dict:
        """获取安全报告

        Returns:
            dict: 安全统计报告
        """
        return {
            "audit_count": self._security.audit_count,
            "tool_audit_count": len(self._tool_guard.get_audit_log()),
            "enabled": self._enabled,
        }

    def start_behavior_session(self) -> None:
        """开始行为监控会话"""
        self._behavior_guard.start_session()

    def reset(self) -> None:
        """重置所有护栏状态"""
        self._behavior_guard = BehaviorGuard()
        self._tool_guard.clear_rate_limits()