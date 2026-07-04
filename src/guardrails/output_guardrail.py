from __future__ import annotations

import re

from src.common.logger import logger
from src.guardrails.base import BaseGuardrail
from src.guardrails.patterns import API_KEY_PATTERNS, HARMFUL_PATTERNS, PASSWORD_PATTERNS, PII_PATTERNS
from src.models.guardrail import GuardrailAction, GuardrailResult, GuardrailSeverity

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_LEAK_PATTERNS = API_KEY_PATTERNS + PASSWORD_PATTERNS + [_SSN_PATTERN]

_MIN_OUTPUT_LENGTH = 1
_MAX_OUTPUT_LENGTH = 50000


class OutputGuardrail(BaseGuardrail):
    name = "output_guardrail"

    def __init__(
        self,
        min_length: int = _MIN_OUTPUT_LENGTH,
        max_length: int = _MAX_OUTPUT_LENGTH,
    ):
        self.min_length = min_length
        self.max_length = max_length

    async def check(self, content: str, **context) -> GuardrailResult:
        result = self._check_length(content)
        if result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return result

        result = self._check_leaks(content)
        if result.action in (GuardrailAction.BLOCK, GuardrailAction.WARN):
            return result

        result = self._check_harmful(content)
        if result.action == GuardrailAction.BLOCK:
            return result

        return self._pass(rule_name=self.name, message="输出检查通过")

    def _check_length(self, content: str) -> GuardrailResult:
        if len(content) < self.min_length:
            return self._block(
                rule_name="output_length",
                message="输出内容为空或过短",
                severity=GuardrailSeverity.LOW,
                details={"length": len(content), "min_length": self.min_length},
            )
        if len(content) > self.max_length:
            return self._warn(
                rule_name="output_length",
                message=f"输出长度 {len(content)} 超过建议上限 {self.max_length}",
                severity=GuardrailSeverity.LOW,
                details={"length": len(content), "max_length": self.max_length},
            )
        return self._pass(rule_name="output_length")

    def _check_leaks(self, content: str) -> GuardrailResult:
        leak_count = 0
        for pattern in _LEAK_PATTERNS:
            if pattern.search(content):
                leak_count += 1

        if leak_count > 0:
            logger.warning("输出包含敏感信息泄露，类型数: %d", leak_count)
            sanitized = self._sanitize_output(content)
            return self._block(
                rule_name="output_leak",
                message="输出包含敏感信息，已自动脱敏",
                severity=GuardrailSeverity.HIGH,
                details={"leaked_type_count": leak_count},
                sanitized_content=sanitized,
            )
        return self._pass(rule_name="output_leak")

    def _check_harmful(self, content: str) -> GuardrailResult:
        matched = []
        for pattern in HARMFUL_PATTERNS:
            m = pattern.search(content)
            if m:
                matched.append(m.group())

        if matched:
            logger.warning("输出包含潜在有害内容，数量: %d", len(matched))
            return self._block(
                rule_name="harmful_content",
                message="输出包含潜在有害内容，已被拦截",
                severity=GuardrailSeverity.CRITICAL,
                details={"matched_count": len(matched)},
            )
        return self._pass(rule_name="harmful_content")

    def _sanitize_output(self, content: str) -> str:
        sanitized = content
        for pattern in _LEAK_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        for pattern in PII_PATTERNS:
            sanitized = pattern.sub("[REDACTED_PII]", sanitized)
        return sanitized