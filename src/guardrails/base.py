from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.guardrail import GuardrailAction, GuardrailResult, GuardrailSeverity


class BaseGuardrail(ABC):
    name: str = ""

    @abstractmethod
    async def check(self, content: str, **context) -> GuardrailResult:
        """检查内容是否通过护栏规则"""

    def _pass(self, rule_name: str = "", message: str = "") -> GuardrailResult:
        return GuardrailResult(
            action=GuardrailAction.PASS,
            rule_name=rule_name or self.name,
            message=message,
        )

    def _block(
        self,
        rule_name: str = "",
        message: str = "",
        severity: GuardrailSeverity = GuardrailSeverity.HIGH,
        details: dict | None = None,
        sanitized_content: str | None = None,
    ) -> GuardrailResult:
        return GuardrailResult(
            action=GuardrailAction.BLOCK,
            rule_name=rule_name or self.name,
            severity=severity,
            message=message,
            details=details or {},
            sanitized_content=sanitized_content,
        )

    def _warn(
        self,
        rule_name: str = "",
        message: str = "",
        severity: GuardrailSeverity = GuardrailSeverity.MEDIUM,
        details: dict | None = None,
        sanitized_content: str | None = None,
    ) -> GuardrailResult:
        return GuardrailResult(
            action=GuardrailAction.WARN,
            rule_name=rule_name or self.name,
            severity=severity,
            message=message,
            details=details or {},
            sanitized_content=sanitized_content,
        )