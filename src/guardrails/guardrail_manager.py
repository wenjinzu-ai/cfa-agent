from __future__ import annotations

from src.common.exceptions import InputGuardrailError, OutputGuardrailError, BehaviorGuardrailError
from src.common.logger import logger
from src.guardrails.base import BaseGuardrail
from src.guardrails.behavior_guardrail import BehaviorGuardrail
from src.guardrails.input_guardrail import InputGuardrail
from src.guardrails.output_guardrail import OutputGuardrail
from src.models.guardrail import GuardrailAction, GuardrailResult


class GuardrailManager:
    def __init__(
        self,
        input_guardrail: InputGuardrail | None = None,
        output_guardrail: OutputGuardrail | None = None,
        behavior_guardrail: BehaviorGuardrail | None = None,
    ):
        self.input = input_guardrail or InputGuardrail()
        self.output = output_guardrail or OutputGuardrail()
        self.behavior = behavior_guardrail or BehaviorGuardrail()
        self._custom_guardrails: list[BaseGuardrail] = []

    def add_guardrail(self, guardrail: BaseGuardrail) -> None:
        self._custom_guardrails.append(guardrail)

    def remove_guardrail(self, name: str) -> None:
        self._custom_guardrails = [g for g in self._custom_guardrails if g.name != name]

    async def check_input(self, content: str, **context) -> GuardrailResult:
        result = await self.input.check(content, **context)
        if result.action == GuardrailAction.BLOCK:
            logger.info("输入被拦截: %s - %s", result.rule_name, result.message)
            raise InputGuardrailError(message=result.message, detail=result.details)
        if result.action == GuardrailAction.WARN:
            logger.warning("输入警告: %s - %s", result.rule_name, result.message)

        for guardrail in self._custom_guardrails:
            custom_result = await guardrail.check(content, **context)
            if custom_result.action == GuardrailAction.BLOCK:
                raise InputGuardrailError(
                    message=custom_result.message, detail=custom_result.details
                )
            if custom_result.action == GuardrailAction.WARN:
                logger.warning("自定义护栏警告: %s - %s", custom_result.rule_name, custom_result.message)
                if result.action == GuardrailAction.PASS:
                    result = custom_result

        return result

    async def check_output(self, content: str, **context) -> GuardrailResult:
        result = await self.output.check(content, **context)
        if result.action == GuardrailAction.BLOCK:
            logger.info("输出被拦截: %s - %s", result.rule_name, result.message)
            if result.sanitized_content is not None:
                return GuardrailResult(
                    action=GuardrailAction.WARN,
                    rule_name=result.rule_name,
                    severity=result.severity,
                    message=result.message,
                    details=result.details,
                    sanitized_content=result.sanitized_content,
                )
            raise OutputGuardrailError(message=result.message, detail=result.details)
        if result.action == GuardrailAction.WARN:
            logger.warning("输出警告: %s - %s", result.rule_name, result.message)

        return result

    async def check_behavior(self, content: str = "", **context) -> GuardrailResult:
        result = await self.behavior.check(content, **context)
        if result.action == GuardrailAction.BLOCK:
            logger.info("行为被拦截: %s - %s", result.rule_name, result.message)
            raise BehaviorGuardrailError(message=result.message, detail=result.details)
        if result.action == GuardrailAction.WARN:
            logger.warning("行为警告: %s - %s", result.rule_name, result.message)
        return result

    async def check_all(self, content: str = "", **context) -> GuardrailResult:
        input_result = await self.check_input(content, **context)
        output_result = await self.check_output(content, **context)
        behavior_result = await self.check_behavior(content, **context)

        results = [input_result, output_result, behavior_result]
        worst = max(
            results,
            key=lambda r: {"pass": 0, "warn": 1, "block": 2}.get(r.action.value, 0),
        )
        return worst

    def get_all_guardrails(self) -> list[BaseGuardrail]:
        guardrails = [self.input, self.output, self.behavior]
        guardrails.extend(self._custom_guardrails)
        return guardrails