import pytest
from pydantic import ValidationError
from src.models.tool import ToolDefinition, ToolResult, ToolPermission


class TestToolDefinition:
    def test_create_definition(self):
        tool_def = ToolDefinition(name="web_search", description="Search the web")
        assert tool_def.name == "web_search"
        assert tool_def.version == "1.0.0"
        assert tool_def.description == "Search the web"
        assert tool_def.parameters == {"type": "object", "properties": {}, "required": []}
        assert tool_def.permissions == []
        assert tool_def.timeout_seconds == 30
        assert tool_def.retry_policy == {"max_retries": 2, "backoff": "exponential"}

    def test_definition_with_typed_permissions(self):
        tool_def = ToolDefinition(
            name="file_read",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            permissions=[ToolPermission.FILE_READ],
            timeout_seconds=60,
        )
        assert tool_def.parameters["required"] == ["path"]
        assert tool_def.permissions[0] == ToolPermission.FILE_READ
        assert tool_def.timeout_seconds == 60

    def test_definition_with_string_permissions_coerced(self):
        tool_def = ToolDefinition(
            name="web_search",
            description="Search the web",
            permissions=["network"],
        )
        assert tool_def.permissions[0] == ToolPermission.NETWORK

    def test_definition_invalid_permission_rejected(self):
        with pytest.raises(ValidationError):
            ToolDefinition(
                name="bad_tool",
                description="Bad",
                permissions=["invalid_permission"],
            )


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"answer": "42"})
        assert result.success is True
        assert result.data == {"answer": "42"}
        assert result.error is None
        assert result.duration_ms == 0.0
        assert result.token_used == 0

    def test_error_result(self):
        result = ToolResult(success=False, error="File not found")
        assert result.success is False
        assert result.error == "File not found"
        assert result.data is None

    def test_result_with_timing(self):
        result = ToolResult(success=True, data="ok", duration_ms=150.5, token_used=30)
        assert result.duration_ms == 150.5
        assert result.token_used == 30


class TestToolPermission:
    def test_permission_values(self):
        assert ToolPermission.FILE_READ == "file_read"
        assert ToolPermission.FILE_WRITE == "file_write"
        assert ToolPermission.NETWORK == "network"
        assert ToolPermission.CODE_EXEC == "code_exec"
        assert ToolPermission.DB_ACCESS == "db_access"
        assert ToolPermission.PRIVILEGED == "privileged"