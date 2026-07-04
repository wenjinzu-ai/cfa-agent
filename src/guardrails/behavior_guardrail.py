from __future__ import annotations

from src.common.config import get_config
from src.common.logger import logger
from src.guardrails.base import BaseGuardrail
from src.models.guardrail import GuardrailAction, GuardrailResult, GuardrailSeverity


class BehaviorGuardrail(BaseGuardrail):
    name = "behavior_guardrail"

    def __init__(
        self,
        max_steps: int | None = None,
        token_budget: int | None = None,
        consecutive_deviation_limit: int | None = None,
    ):
        config = get_config().behavior_guard
        self.max_steps = max_steps if max_steps is not None else config.max_steps
        self.token_budget = token_budget if token_budget is not None else config.token_budget
        self.consecutive_deviation_limit = (
            consecutive_deviation_limit
            if consecutive_deviation_limit is not None
            else config.consecutive_deviation_limit
        )

        self._step_count: int = 0
        self._tokens_used: int = 0
        self._consecutive_deviations: int = 0
        self._plan_goal: str = ""
        self._plan_steps: list[str] = []

    def reset(self) -> None:
        self._step_count = 0
        self._tokens_used = 0
        self._consecutive_deviations = 0
        self._plan_goal = ""
        self._plan_steps = []

    def set_plan_goal(self, goal: str, steps: list[str] | None = None) -> None:
        self._plan_goal = goal
        self._plan_steps = steps or []

    def record_step(self) -> None:
        self._step_count += 1

    def record_tokens(self, tokens: int) -> None:
        self._tokens_used += tokens

    async def check(self, content: str = "", **context) -> GuardrailResult:
        step_result = self._check_step_limit()
        if step_result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return step_result

        token_result = self._check_token_budget()
        if token_result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return token_result

        deviation_result = self._check_deviation(content)
        if deviation_result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return deviation_result

        return self._pass(rule_name=self.name, message="行为检查通过")

    def _check_step_limit(self) -> GuardrailResult:
        if self._step_count >= self.max_steps:
            logger.warning("步骤数 %d 达到上限 %d", self._step_count, self.max_steps)
            return self._block(
                rule_name="step_limit",
                message=f"执行步骤数已达上限 {self.max_steps}",
                severity=GuardrailSeverity.HIGH,
                details={
                    "step_count": self._step_count,
                    "max_steps": self.max_steps,
                },
            )
        if self._step_count >= self.max_steps * 0.8:
            return self._warn(
                rule_name="step_limit",
                message=f"步骤数 {self._step_count} 接近上限 {self.max_steps}",
                severity=GuardrailSeverity.MEDIUM,
                details={
                    "step_count": self._step_count,
                    "max_steps": self.max_steps,
                },
            )
        return self._pass(rule_name="step_limit")

    def _check_token_budget(self) -> GuardrailResult:
        if self._tokens_used >= self.token_budget:
            logger.warning("Token 使用量 %d 超出预算 %d", self._tokens_used, self.token_budget)
            return self._block(
                rule_name="token_budget",
                message=f"Token 使用量已达预算上限 {self.token_budget}",
                severity=GuardrailSeverity.HIGH,
                details={
                    "tokens_used": self._tokens_used,
                    "token_budget": self.token_budget,
                },
            )
        if self._tokens_used >= self.token_budget * 0.8:
            return self._warn(
                rule_name="token_budget",
                message=f"Token 使用量 {self._tokens_used} 接近预算上限 {self.token_budget}",
                severity=GuardrailSeverity.MEDIUM,
                details={
                    "tokens_used": self._tokens_used,
                    "token_budget": self.token_budget,
                },
            )
        return self._pass(rule_name="token_budget")

    def _check_deviation(self, content: str) -> GuardrailResult:
        if not self._plan_goal or not content:
            return self._pass(rule_name="plan_deviation")

        if self._plan_steps:
            is_in_plan = self._is_step_in_plan(content)
            if not is_in_plan:
                self._consecutive_deviations += 1
                logger.info(
                    "偏离检测: step=[%s] 不在 plan 步骤列表中 (连续偏离: %d)",
                    content[:40], self._consecutive_deviations,
                )
            else:
                self._consecutive_deviations = 0

        if self._consecutive_deviations >= self.consecutive_deviation_limit:
            logger.warning(
                "连续偏离计划 %d 次，达到限制 %d",
                self._consecutive_deviations,
                self.consecutive_deviation_limit,
            )
            return self._block(
                rule_name="plan_deviation",
                message=f"连续偏离计划目标 {self.consecutive_deviation_limit} 次，执行被终止",
                severity=GuardrailSeverity.HIGH,
                details={
                    "consecutive_deviations": self._consecutive_deviations,
                    "deviation_limit": self.consecutive_deviation_limit,
                },
            )

        if self._consecutive_deviations > 0:
            return self._warn(
                rule_name="plan_deviation",
                message="当前步骤不在计划步骤列表中",
                severity=GuardrailSeverity.MEDIUM,
                details={
                    "consecutive_deviations": self._consecutive_deviations,
                },
            )

        return self._pass(rule_name="plan_deviation")

    def _is_step_in_plan(self, step_description: str) -> bool:
        step_lower = step_description.lower().strip()
        for plan_step in self._plan_steps:
            plan_lower = plan_step.lower().strip()
            if step_lower == plan_lower:
                return True
            if step_lower in plan_lower or plan_lower in step_lower:
                return True
            if self._keyword_overlap_ratio(step_lower, plan_lower) >= 0.5:
                return True
        return False

    @staticmethod
    def _keyword_overlap_ratio(text_a: str, text_b: str) -> float:
        words_a = set(text_a.split())
        words_b = set(text_b.split())
        if not words_a or not words_b:
            return 0.0
        overlap = len(words_a & words_b)
        return overlap / min(len(words_a), len(words_b))