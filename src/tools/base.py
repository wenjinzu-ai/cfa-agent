from __future__ import annotations

from abc import ABC, abstractmethod

import jsonschema

from src.models.tool import ToolDefinition, ToolPermission, ToolResult


class BaseTool(ABC):
    definition: ToolDefinition

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """执行工具，返回结果"""

    async def validate_params(self, params: dict) -> tuple[bool, str]:
        try:
            jsonschema.validate(params, self.definition.parameters)
            return True, ""
        except jsonschema.ValidationError as e:
            return False, str(e.message)

    def has_permission(self, required: list[ToolPermission]) -> bool:
        tool_perms = {p.value for p in self.definition.permissions}
        req_perms = {p.value for p in required}
        return req_perms.issubset(tool_perms)