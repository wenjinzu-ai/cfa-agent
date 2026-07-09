"""CFA-Agent 行为护栏

操作限制：限制智能体的操作范围和频率
异常检测：检测 ReAct 循环中的异常行为
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from src.common.exceptions import GuardrailViolationError

logger = logging.getLogger("cfa-agent.guardrails.behavior")


class BehaviorGuard:
    """行为护栏

    职责：
    - 限制最大迭代次数
    - 限制 Token 预算
    - 检测连续偏差
    - 检测循环行为
    - 触发告警或终止
    """

    def __init__(
        self,
        max_steps: int = 20,
        token_budget: int = 50000,
        deviation_threshold: float = 0.6,
        consecutive_deviation_limit: int = 5,
        max_consecutive_failures: int = 3,
        max_execution_time: float = 300.0,
        loop_detection_window: int = 5,
    ):
        self._max_steps = max_steps
        self._token_budget = token_budget
        self._deviation_threshold = deviation_threshold
        self._consecutive_deviation_limit = consecutive_deviation_limit
        self._max_consecutive_failures = max_consecutive_failures
        self._max_execution_time = max_execution_time
        self._loop_detection_window = loop_detection_window
        self._start_time: Optional[float] = None
        self._action_history: list[str] = []

    def start_session(self) -> None:
        """开始一个新的会话追踪"""
        self._start_time = time.time()
        self._action_history = []

    async def check_step_limit(self, current_step: int) -> dict:
        """检查步数限制

        Args:
            current_step: 当前步数

        Returns:
            dict: {"allowed": bool, "reason": str | None, "remaining": int}
        """
        remaining = self._max_steps - current_step

        if current_step >= self._max_steps:
            logger.warning(f"Step limit reached: {current_step}/{self._max_steps}")
            return {
                "allowed": False,
                "reason": f"已达到最大步数限制（{self._max_steps}步）",
                "remaining": 0,
            }

        if remaining <= 3:
            logger.warning(f"Approaching step limit: {remaining} steps remaining")

        return {
            "allowed": True,
            "reason": None,
            "remaining": remaining,
        }

    async def check_token_budget(self, used_tokens: int) -> dict:
        """检查 Token 预算

        Args:
            used_tokens: 已使用的 Token 数

        Returns:
            dict: {"allowed": bool, "reason": str | None, "remaining": int, "usage_ratio": float}
        """
        remaining = self._token_budget - used_tokens
        usage_ratio = used_tokens / self._token_budget if self._token_budget > 0 else 0.0

        if used_tokens >= self._token_budget:
            logger.warning(f"Token budget exhausted: {used_tokens}/{self._token_budget}")
            return {
                "allowed": False,
                "reason": f"Token 预算已耗尽（{used_tokens}/{self._token_budget}）",
                "remaining": 0,
                "usage_ratio": usage_ratio,
            }

        if usage_ratio >= 0.8:
            logger.warning(f"Token budget approaching limit: {usage_ratio:.1%}")

        return {
            "allowed": True,
            "reason": None,
            "remaining": remaining,
            "usage_ratio": usage_ratio,
        }

    async def check_deviation(self, deviation_score: float, consecutive_count: int) -> dict:
        """检查偏差

        Args:
            deviation_score: 偏差分数（0-1）
            consecutive_count: 连续偏差次数

        Returns:
            dict: {"allowed": bool, "reason": str | None, "should_reflect": bool}
        """
        should_reflect = False

        if deviation_score >= self._deviation_threshold:
            if consecutive_count >= self._consecutive_deviation_limit:
                logger.warning(
                    f"Deviation limit reached: score={deviation_score}, "
                    f"consecutive={consecutive_count}/{self._consecutive_deviation_limit}"
                )
                return {
                    "allowed": False,
                    "reason": f"连续偏差次数超限（{consecutive_count}次，阈值{self._consecutive_deviation_limit}）",
                    "should_reflect": True,
                }

            should_reflect = True
            logger.info(f"Deviation detected: score={deviation_score}, suggesting reflection")

        return {
            "allowed": True,
            "reason": None,
            "should_reflect": should_reflect,
        }

    async def check_consecutive_failures(self, failure_count: int) -> dict:
        """检查连续失败次数

        Args:
            failure_count: 连续失败次数

        Returns:
            dict: {"allowed": bool, "reason": str | None, "should_reflect": bool}
        """
        if failure_count >= self._max_consecutive_failures:
            logger.warning(f"Consecutive failure limit reached: {failure_count}/{self._max_consecutive_failures}")
            return {
                "allowed": False,
                "reason": f"连续失败次数超限（{failure_count}次，阈值{self._max_consecutive_failures}）",
                "should_reflect": True,
            }

        if failure_count >= 2:
            return {
                "allowed": True,
                "reason": None,
                "should_reflect": True,
            }

        return {
            "allowed": True,
            "reason": None,
            "should_reflect": False,
        }

    async def check_execution_time(self) -> dict:
        """检查执行时间

        Returns:
            dict: {"allowed": bool, "reason": str | None, "elapsed": float}
        """
        if self._start_time is None:
            return {"allowed": True, "reason": None, "elapsed": 0.0}

        elapsed = time.time() - self._start_time

        if elapsed >= self._max_execution_time:
            logger.warning(f"Execution time limit reached: {elapsed:.1f}s/{self._max_execution_time}s")
            return {
                "allowed": False,
                "reason": f"执行时间超限（{elapsed:.1f}s/{self._max_execution_time}s）",
                "elapsed": elapsed,
            }

        return {
            "allowed": True,
            "reason": None,
            "elapsed": elapsed,
        }

    async def check_loop(self, action_signature: str) -> dict:
        """检测循环行为

        检查最近 N 步中是否存在重复的动作模式

        Args:
            action_signature: 当前动作的签名（如 "tool_name:args_hash"）

        Returns:
            dict: {"allowed": bool, "reason": str | None, "loop_detected": bool}
        """
        self._action_history.append(action_signature)

        if len(self._action_history) < 3:
            return {"allowed": True, "reason": None, "loop_detected": False}

        window = self._action_history[-self._loop_detection_window:]

        if len(window) >= 3:
            for pattern_len in range(1, len(window) // 2 + 1):
                pattern = window[-pattern_len:]
                previous = window[-pattern_len * 2:-pattern_len]
                if pattern == previous and pattern_len >= 1:
                    logger.warning(f"Loop detected: pattern of length {pattern_len} repeated")
                    return {
                        "allowed": False,
                        "reason": f"检测到循环行为：长度为{pattern_len}的模式重复出现",
                        "loop_detected": True,
                    }

        return {"allowed": True, "reason": None, "loop_detected": False}

    async def full_check(
        self,
        current_step: int,
        used_tokens: int,
        deviation_score: float = 0.0,
        consecutive_deviation_count: int = 0,
        consecutive_failures: int = 0,
        action_signature: str = "",
    ) -> dict:
        """执行完整的行为检查

        Args:
            current_step: 当前步数
            used_tokens: 已使用 Token 数
            deviation_score: 偏差分数
            consecutive_deviation_count: 连续偏差次数
            consecutive_failures: 连续失败次数
            action_signature: 动作签名

        Returns:
            dict: {
                "allowed": bool,
                "reasons": list[str],
                "should_reflect": bool,
                "checks": dict,
            }
        """
        reasons = []
        should_reflect = False
        checks = {}

        step_check = await self.check_step_limit(current_step)
        checks["step"] = step_check
        if not step_check["allowed"]:
            reasons.append(step_check["reason"])

        token_check = await self.check_token_budget(used_tokens)
        checks["token"] = token_check
        if not token_check["allowed"]:
            reasons.append(token_check["reason"])

        if deviation_score > 0:
            deviation_check = await self.check_deviation(deviation_score, consecutive_deviation_count)
            checks["deviation"] = deviation_check
            if not deviation_check["allowed"]:
                reasons.append(deviation_check["reason"])
            if deviation_check.get("should_reflect"):
                should_reflect = True

        failure_check = await self.check_consecutive_failures(consecutive_failures)
        checks["failures"] = failure_check
        if not failure_check["allowed"]:
            reasons.append(failure_check["reason"])
        if failure_check.get("should_reflect"):
            should_reflect = True

        time_check = await self.check_execution_time()
        checks["time"] = time_check
        if not time_check["allowed"]:
            reasons.append(time_check["reason"])

        if action_signature:
            loop_check = await self.check_loop(action_signature)
            checks["loop"] = loop_check
            if not loop_check["allowed"]:
                reasons.append(loop_check["reason"])

        allowed = len(reasons) == 0

        return {
            "allowed": allowed,
            "reasons": reasons,
            "should_reflect": should_reflect,
            "checks": checks,
        }