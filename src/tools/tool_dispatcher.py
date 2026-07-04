from __future__ import annotations

import asyncio
import time

from src.common.exceptions import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolTimeoutError,
)
from src.common.logger import logger
from src.models.tool import ToolPermission, ToolResult
from src.tools.registry import ToolRegistry


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry.get_instance()

    async def dispatch(
        self,
        tool_name: str,
        params: dict,
        allowed_permissions: list[ToolPermission] | None = None,
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFoundError(detail={"tool_name": tool_name})

        if allowed_permissions and not tool.has_permission(allowed_permissions):
            raise ToolPermissionError(detail={"tool_name": tool_name})

        valid, err = await tool.validate_params(params)
        if not valid:
            raise ToolExecutionError(detail={"tool_name": tool_name, "error": err})

        timeout = tool.definition.timeout_seconds
        try:
            start = time.monotonic()
            result = await asyncio.wait_for(
                tool.execute(**params),
                timeout=timeout,
            )
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except asyncio.TimeoutError:
            raise ToolTimeoutError(detail={"tool_name": tool_name, "timeout": timeout})
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(detail={"tool_name": tool_name, "error": str(e)})

    async def dispatch_with_retry(
        self,
        tool_name: str,
        params: dict,
        allowed_permissions: list[ToolPermission] | None = None,
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFoundError(detail={"tool_name": tool_name})

        max_retries = tool.definition.retry_policy.get("max_retries", 2)
        backoff_type = tool.definition.retry_policy.get("backoff", "exponential")

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self.dispatch(tool_name, params, allowed_permissions)
            except ToolPermissionError:
                raise
            except (ToolTimeoutError, ToolExecutionError) as e:
                last_error = e
                if attempt < max_retries:
                    delay = 2**attempt if backoff_type == "exponential" else 1
                    logger.warning(
                        "工具 %s 第 %d 次重试，等待 %ds", tool_name, attempt + 1, delay
                    )
                    await asyncio.sleep(delay)

        raise last_error or ToolExecutionError(detail={"tool_name": tool_name, "error": "unknown"})