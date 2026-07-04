from __future__ import annotations

import re

from src.common.logger import logger
from src.guardrails.base import BaseGuardrail
from src.guardrails.patterns import API_KEY_PATTERNS, INJECTION_PATTERNS, PASSWORD_PATTERNS, PII_PATTERNS
from src.models.guardrail import GuardrailAction, GuardrailResult, GuardrailSeverity

_MAX_INPUT_LENGTH = 10000


class InputGuardrail(BaseGuardrail):
    name = "input_guardrail"

    def __init__(self, max_length: int = _MAX_INPUT_LENGTH):
        self.max_length = max_length

    async def check(self, content: str, **context) -> GuardrailResult:
        result = self._check_length(content)
        if result.action == GuardrailAction.BLOCK:
            return result

        result = self._check_injection(content)
        if result.action == GuardrailAction.BLOCK:
            return result

        result = self._check_sensitive_info(content)
        if result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return result

        return self._pass(rule_name=self.name, message="输入检查通过")

    def _check_length(self, content: str) -> GuardrailResult:
        if len(content) > self.max_length:
            return self._block(
                rule_name="input_length",
                message=f"输入长度 {len(content)} 超过限制 {self.max_length}",
                severity=GuardrailSeverity.LOW,
                details={"length": len(content), "max_length": self.max_length},
            )
        return self._pass(rule_name="input_length")

    def _check_injection(self, content: str) -> GuardrailResult:
        matched = []
        for pattern in INJECTION_PATTERNS:
            m = pattern.search(content)
            if m:
                matched.append(m.group())

        if matched:
            logger.warning("检测到提示注入攻击: %s", matched)
            return self._block(
                rule_name="prompt_injection",
                message="检测到潜在的提示注入攻击",
                severity=GuardrailSeverity.CRITICAL,
                details={"matched_patterns": matched},
            )
        return self._pass(rule_name="prompt_injection")

    def _check_sensitive_info(self, content: str) -> GuardrailResult:
        detected_types: list[str] = []

        for pattern in API_KEY_PATTERNS:
            if pattern.search(content):
                detected_types.append("api_key")

        for pattern in PASSWORD_PATTERNS:
            if pattern.search(content):
                detected_types.append("password")

        for pattern in PII_PATTERNS:
            if pattern.search(content):
                detected_types.append("pii")

        if detected_types:
            sanitized = self._sanitize_content(content)
            has_credential = "api_key" in detected_types or "password" in detected_types
            severity = GuardrailSeverity.HIGH if has_credential else GuardrailSeverity.MEDIUM
            message = (
                "输入包含敏感信息（API Key/密码），已自动脱敏"
                if has_credential
                else "输入可能包含个人身份信息，已自动脱敏"
            )
            return self._warn(
                rule_name="sensitive_info",
                message=message,
                severity=severity,
                details={"detected_types": detected_types},
                sanitized_content=sanitized,
            )

        return self._pass(rule_name="sensitive_info")

    def _sanitize_content(self, content: str) -> str:
        sanitized = content
        for pattern in API_KEY_PATTERNS:
            sanitized = pattern.sub("[REDACTED_API_KEY]", sanitized)
        for pattern in PASSWORD_PATTERNS:
            sanitized = pattern.sub(
                lambda m: _redact_password_match(m),
                sanitized,
            )
        for pattern in PII_PATTERNS:
            sanitized = pattern.sub("[REDACTED_PII]", sanitized)
        return sanitized


def _redact_password_match(m: re.Match) -> str:
    text = m.group()
    for sep in ("=", ":"):
        if sep in text:
            key = text[: text.index(sep) + 1]
            return f"{key} [REDACTED]"
    return "[REDACTED]"