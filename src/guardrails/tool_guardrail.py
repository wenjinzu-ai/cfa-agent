from __future__ import annotations

from src.common.logger import logger
from src.guardrails.base import BaseGuardrail
from src.models.guardrail import GuardrailResult, GuardrailSeverity
from src.models.tool import ToolPermission


class ToolGuardrail(BaseGuardrail):
    name = "tool_guardrail"

    ALLOWED_PERMISSIONS_MAP: dict[str, list[ToolPermission]] = {
        "default": [ToolPermission.FILE_READ, ToolPermission.NETWORK],
        "elevated": list(ToolPermission),
    }

    def __init__(self, mode: str = "default"):
        self._mode = mode
        self._allowed = self.ALLOWED_PERMISSIONS_MAP.get(
            mode, self.ALLOWED_PERMISSIONS_MAP["default"]
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def allowed_permissions(self) -> list[ToolPermission]:
        return list(self._allowed)

    async def check(self, content: str = "", **context) -> GuardrailResult:
        tool_name = context.get("tool_name", "")
        required = context.get("required_permissions", [])
        if required and not self.check_permission(tool_name, required):
            return self._block(
                rule_name="tool_permission",
                message=f"工具 {tool_name} 所需权限不足",
                severity=GuardrailSeverity.HIGH,
                details={
                    "tool_name": tool_name,
                    "required": [p.value for p in required],
                    "allowed": [p.value for p in self._allowed],
                },
            )
        return self._pass(rule_name=self.name, message="工具权限检查通过")

    def check_permission(self, tool_name: str, required: list[ToolPermission]) -> bool:
        result = all(p in self._allowed for p in required)
        if not result:
            logger.warning(
                "工具 %s 权限不足: 需要 %s, 允许 %s",
                tool_name,
                [p.value for p in required],
                [p.value for p in self._allowed],
            )
        return result

    def filter_sensitive_params(self, tool_name: str, params: dict) -> dict:
        sensitive_keys = {"password", "token", "secret", "api_key"}
        return {
            k: "***" if any(s in k.lower() for s in sensitive_keys) else v
            for k, v in params.items()
        }