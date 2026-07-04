from __future__ import annotations

import pytest

from src.guardrails.tool_guardrail import ToolGuardrail
from src.models.guardrail import GuardrailAction
from src.models.tool import ToolPermission


class TestToolGuardrailPermission:
    @pytest.mark.asyncio
    async def test_default_mode_allows_file_read(self):
        guard = ToolGuardrail(mode="default")
        assert guard.check_permission("file_reader", [ToolPermission.FILE_READ]) is True

    @pytest.mark.asyncio
    async def test_default_mode_allows_network(self):
        guard = ToolGuardrail(mode="default")
        assert guard.check_permission("web_search", [ToolPermission.NETWORK]) is True

    @pytest.mark.asyncio
    async def test_default_mode_denies_file_write(self):
        guard = ToolGuardrail(mode="default")
        assert guard.check_permission("file_writer", [ToolPermission.FILE_WRITE]) is False

    @pytest.mark.asyncio
    async def test_default_mode_denies_code_exec(self):
        guard = ToolGuardrail(mode="default")
        assert guard.check_permission("runner", [ToolPermission.CODE_EXEC]) is False

    @pytest.mark.asyncio
    async def test_elevated_mode_allows_all(self):
        guard = ToolGuardrail(mode="elevated")
        for perm in ToolPermission:
            assert guard.check_permission("tool", [perm]) is True

    @pytest.mark.asyncio
    async def test_invalid_mode_falls_back_to_default(self):
        guard = ToolGuardrail(mode="unknown")
        assert guard.check_permission("tool", [ToolPermission.FILE_READ]) is True
        assert guard.check_permission("tool", [ToolPermission.FILE_WRITE]) is False

    @pytest.mark.asyncio
    async def test_multiple_permissions_all_required(self):
        guard = ToolGuardrail(mode="default")
        assert guard.check_permission("tool", [ToolPermission.FILE_READ, ToolPermission.NETWORK]) is True
        assert guard.check_permission("tool", [ToolPermission.FILE_READ, ToolPermission.FILE_WRITE]) is False


class TestToolGuardrailCheck:
    @pytest.mark.asyncio
    async def test_check_passes_when_no_required_permissions(self):
        guard = ToolGuardrail(mode="default")
        result = await guard.check(content="", tool_name="tool", required_permissions=[])
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_check_blocks_insufficient_permissions(self):
        guard = ToolGuardrail(mode="default")
        result = await guard.check(
            content="",
            tool_name="runner",
            required_permissions=[ToolPermission.CODE_EXEC],
        )
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "tool_permission"

    @pytest.mark.asyncio
    async def test_check_passes_with_sufficient_permissions(self):
        guard = ToolGuardrail(mode="elevated")
        result = await guard.check(
            content="",
            tool_name="runner",
            required_permissions=[ToolPermission.CODE_EXEC],
        )
        assert result.action == GuardrailAction.PASS


class TestToolGuardrailFilterParams:
    def test_filter_masks_password(self):
        guard = ToolGuardrail()
        params = {"username": "admin", "password": "secret123"}
        filtered = guard.filter_sensitive_params("tool", params)
        assert filtered["username"] == "admin"
        assert filtered["password"] == "***"

    def test_filter_masks_token(self):
        guard = ToolGuardrail()
        params = {"access_token": "abc123", "query": "test"}
        filtered = guard.filter_sensitive_params("tool", params)
        assert filtered["access_token"] == "***"
        assert filtered["query"] == "test"

    def test_filter_masks_api_key(self):
        guard = ToolGuardrail()
        params = {"api_key": "sk-xxx", "model": "gpt-4"}
        filtered = guard.filter_sensitive_params("tool", params)
        assert filtered["api_key"] == "***"
        assert filtered["model"] == "gpt-4"

    def test_filter_preserves_normal_params(self):
        guard = ToolGuardrail()
        params = {"query": "python", "limit": 10}
        filtered = guard.filter_sensitive_params("tool", params)
        assert filtered == params

    def test_filter_masks_secret(self):
        guard = ToolGuardrail()
        params = {"client_secret": "xyz", "name": "app"}
        filtered = guard.filter_sensitive_params("tool", params)
        assert filtered["client_secret"] == "***"
        assert filtered["name"] == "app"


class TestToolGuardrailProperties:
    def test_mode_property(self):
        guard = ToolGuardrail(mode="elevated")
        assert guard.mode == "elevated"

    def test_allowed_permissions_default(self):
        guard = ToolGuardrail(mode="default")
        allowed = guard.allowed_permissions
        assert ToolPermission.FILE_READ in allowed
        assert ToolPermission.NETWORK in allowed
        assert ToolPermission.FILE_WRITE not in allowed

    def test_allowed_permissions_elevated(self):
        guard = ToolGuardrail(mode="elevated")
        allowed = guard.allowed_permissions
        assert len(allowed) == len(ToolPermission)