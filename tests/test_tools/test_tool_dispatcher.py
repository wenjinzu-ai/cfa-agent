import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.common.exceptions import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolTimeoutError,
)
from src.models.tool import ToolDefinition, ToolPermission, ToolResult
from src.tools.base import BaseTool
from src.tools.registry import ToolRegistry
from src.tools.tool_dispatcher import ToolDispatcher


class FastTool(BaseTool):
    definition = ToolDefinition(
        name="fast_tool",
        version="1.0.0",
        description="A fast tool",
        parameters={
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
            "required": ["value"],
        },
        permissions=[ToolPermission.FILE_READ],
        timeout_seconds=10,
    )

    async def execute(self, value: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"echo": value})


class SlowTool(BaseTool):
    definition = ToolDefinition(
        name="slow_tool",
        version="1.0.0",
        description="A slow tool that times out",
        parameters={"type": "object", "properties": {}, "required": []},
        permissions=[ToolPermission.NETWORK],
        timeout_seconds=1,
    )

    async def execute(self, **kwargs) -> ToolResult:
        await asyncio.sleep(10)
        return ToolResult(success=True)


class FailingTool(BaseTool):
    definition = ToolDefinition(
        name="failing_tool",
        version="1.0.0",
        description="A tool that always fails",
        parameters={"type": "object", "properties": {}, "required": []},
        permissions=[],
        timeout_seconds=5,
        retry_policy={"max_retries": 2, "backoff": "exponential"},
    )

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("intentional failure")


class PermissionTool(BaseTool):
    definition = ToolDefinition(
        name="perm_tool",
        version="1.0.0",
        description="A tool with specific permissions",
        parameters={"type": "object", "properties": {}, "required": []},
        permissions=[ToolPermission.FILE_READ],
        timeout_seconds=5,
    )

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True)


@pytest.fixture(autouse=True)
def reset_registry():
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


@pytest.fixture
def dispatcher():
    return ToolDispatcher()


def _reg():
    return ToolRegistry.get_instance()


class TestToolDispatcherDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_success(self, dispatcher):
        _reg().register(FastTool)
        result = await dispatcher.dispatch("fast_tool", {"value": "hello"})
        assert result.success is True
        assert result.data["echo"] == "hello"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_dispatch_tool_not_found(self, dispatcher):
        with pytest.raises(ToolNotFoundError) as exc_info:
            await dispatcher.dispatch("nonexistent", {})
        assert "nonexistent" in exc_info.value.detail.get("tool_name", "")

    @pytest.mark.asyncio
    async def test_dispatch_invalid_params(self, dispatcher):
        _reg().register(FastTool)
        with pytest.raises(ToolExecutionError) as exc_info:
            await dispatcher.dispatch("fast_tool", {})
        assert "fast_tool" in exc_info.value.detail.get("tool_name", "")

    @pytest.mark.asyncio
    async def test_dispatch_timeout(self, dispatcher):
        _reg().register(SlowTool)
        with pytest.raises(ToolTimeoutError) as exc_info:
            await dispatcher.dispatch("slow_tool", {})
        assert "slow_tool" in exc_info.value.detail.get("tool_name", "")

    @pytest.mark.asyncio
    async def test_dispatch_execution_error(self, dispatcher):
        _reg().register(FailingTool)
        with pytest.raises(ToolExecutionError) as exc_info:
            await dispatcher.dispatch("failing_tool", {})
        assert "failing_tool" in exc_info.value.detail.get("tool_name", "")

    @pytest.mark.asyncio
    async def test_dispatch_permission_check_pass(self, dispatcher):
        _reg().register(PermissionTool)
        result = await dispatcher.dispatch(
            "perm_tool", {}, allowed_permissions=[ToolPermission.FILE_READ]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_permission_check_fail(self, dispatcher):
        _reg().register(PermissionTool)
        with pytest.raises(ToolPermissionError) as exc_info:
            await dispatcher.dispatch(
                "perm_tool", {}, allowed_permissions=[ToolPermission.NETWORK]
            )
        assert "perm_tool" in exc_info.value.detail.get("tool_name", "")


class TestToolDispatcherRetry:
    @pytest.mark.asyncio
    async def test_retry_eventually_succeeds(self, dispatcher):
        call_count = 0

        class FlakeyTool(BaseTool):
            definition = ToolDefinition(
                name="flakey_tool",
                version="1.0.0",
                description="Flakey tool",
                parameters={"type": "object", "properties": {}, "required": []},
                timeout_seconds=5,
                retry_policy={"max_retries": 3, "backoff": "exponential"},
            )

            async def execute(self, **kwargs) -> ToolResult:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ToolExecutionError(detail={"error": "transient"})
                return ToolResult(success=True, data={"attempt": call_count})

        _reg().register(FlakeyTool)

        with patch("src.tools.tool_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            result = await dispatcher.dispatch_with_retry("flakey_tool", {})
        assert result.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, dispatcher):
        _reg().register(FailingTool)

        with patch("src.tools.tool_dispatcher.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ToolExecutionError):
                await dispatcher.dispatch_with_retry("failing_tool", {})

    @pytest.mark.asyncio
    async def test_retry_not_found_no_retry(self, dispatcher):
        with pytest.raises(ToolNotFoundError):
            await dispatcher.dispatch_with_retry("nonexistent", {})

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self, dispatcher):
        sleep_delays = []

        class AlwaysFailTool(BaseTool):
            definition = ToolDefinition(
                name="always_fail",
                version="1.0.0",
                description="Always fails",
                parameters={"type": "object", "properties": {}, "required": []},
                timeout_seconds=5,
                retry_policy={"max_retries": 2, "backoff": "exponential"},
            )

            async def execute(self, **kwargs) -> ToolResult:
                raise ToolExecutionError(detail={"error": "fail"})

        _reg().register(AlwaysFailTool)

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        with patch("src.tools.tool_dispatcher.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ToolExecutionError):
                await dispatcher.dispatch_with_retry("always_fail", {})

        assert len(sleep_delays) == 2
        assert sleep_delays[0] == 1
        assert sleep_delays[1] == 2