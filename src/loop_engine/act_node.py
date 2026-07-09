"""CFA-Agent 执行节点

act 节点：调用 Tool/MCP 工具

技术方案 §7.5.2：
1. 接收 pending_action.tool_calls（标准 Function Calling 格式）
2. 遍历 tool_calls，从 ToolRegistry 或 MCP ToolManager 查找工具
3. 执行工具调用，设置超时
4. 将工具返回结果封装为 ToolMessage
5. 捕获异常并记录

流式委派（StreamWriter）：
- 当工具为 delegate 时，使用 astream_execute() 流式执行子智能体
- 子智能体事件通过 writer() 实时推送到父图的 custom 流
- 前端通过 astream_run() 的 custom 事件统一接收

错误处理：
- 工具不存在 → 返回错误信息给 think 重新决策
- 工具超时 → 设置超时时间（默认 30s），返回降级信息
- 工具执行失败 → 返回错误详情，让 think 决定是否重试
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from langgraph.types import StreamWriter

from src.loop_engine.state import ReActState, create_step
from src.tools.registry import ToolRegistry

logger = logging.getLogger("cfa-agent.loop_engine.act")


class ActNode:
    """执行节点

    职责：
    - 解析 LLM 返回的 tool_calls
    - 调用对应的 Tool 或 MCP 工具
    - 收集执行结果和错误信息
    - 处理工具执行的超时和异常

    Attributes:
        _tool_registry: 工具注册中心
        _default_timeout: 默认超时时间（秒）
        _max_concurrent: 最大并发数
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        default_timeout: float = 30.0,
        max_concurrent: int = 3,
        tool_names: Optional[list[str]] = None,
    ):
        self._tool_registry = tool_registry
        self._default_timeout = default_timeout
        self._max_concurrent = max_concurrent
        self._tool_names: list[str] = tool_names if tool_names is not None else []

    async def execute(self, state: ReActState, *, writer: StreamWriter) -> dict:
        """执行工具调用

        当工具为 delegate 时，使用 astream_execute() 流式执行子智能体，
        子智能体事件通过 writer() 实时推送到父图的 custom 流。

        Args:
            state: 当前状态（包含 tool_calls）
            writer: LangGraph StreamWriter，用于推送自定义事件

        Returns:
            dict: 状态更新（包含工具执行结果）
        """
        pending_action = state.get("pending_action")
        if not pending_action or not pending_action.get("tool_calls"):
            logger.warning("No tool calls to execute")
            return {
                "last_observation": "无待执行的工具调用",
            }

        tool_calls = pending_action["tool_calls"]
        logger.info(f"Executing {len(tool_calls)} tool call(s)")

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _execute_single(tc: dict) -> dict:
            async with semaphore:
                return await self._execute_tool_call(tc, writer=writer)

        results = await asyncio.gather(
            *[_execute_single(tc) for tc in tool_calls],
            return_exceptions=True,
        )

        observations = []
        all_success = True
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Tool call {i} raised exception: {result}")
                observations.append({
                    "tool_call_id": tool_calls[i].get("id", str(i)),
                    "tool_name": tool_calls[i].get("name", "unknown"),
                    "status": "error",
                    "error": str(result),
                    "result": None,
                })
                all_success = False
            else:
                observations.append(result)
                if result.get("status") != "success":
                    all_success = False

        observation_text = self._format_observations(observations)

        return {
            "last_observation": observation_text,
            "consecutive_failures": state.get("consecutive_failures", 0) + (0 if all_success else 1),
        }

    async def _execute_tool_call(self, tc: dict, *, writer: StreamWriter) -> dict:
        """执行单个工具调用

        当工具为 delegate 且支持 astream_execute 时，使用流式执行，
        子智能体事件通过 writer() 实时推送到父图的 custom 流。

        Args:
            tc: 工具调用信息（name, args, id）
            writer: LangGraph StreamWriter

        Returns:
            dict: 执行结果
        """
        tool_name = tc.get("name", "")
        args = tc.get("args", {})
        tool_call_id = tc.get("id", "")

        start_time = time.time()

        try:
            try:
                tool = self._tool_registry.get(tool_name)
            except Exception:
                tool = None

            if not tool:
                tool = self._fuzzy_match_tool(tool_name)
                if tool:
                    logger.info(f"Fuzzy matched tool: {tool_name} -> {tool.name}")
                    tool_name = tool.name
                else:
                    available = ", ".join(t.name for t in self._get_allowed_tools())
                    return {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": "not_found",
                        "error": f"工具 '{tool_name}' 不存在。可用工具: {available}",
                        "result": None,
                        "duration_ms": int((time.time() - start_time) * 1000),
                    }

            if self._tool_names and tool_name not in self._tool_names:
                available = ", ".join(self._tool_names)
                return {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": "forbidden",
                    "error": f"工具 '{tool_name}' 不在当前智能体的可用列表中。可用工具: {available}",
                    "result": None,
                    "duration_ms": int((time.time() - start_time) * 1000),
                }

            logger.info(f"Executing tool: {tool_name} with args: {json.dumps(args, ensure_ascii=False)[:200]}")

            if tool_name == "delegate" and hasattr(tool, "astream_execute"):
                return await self._execute_delegate_stream(tool, args, tool_call_id, writer=writer, start_time=start_time)

            result = await asyncio.wait_for(
                tool.safe_execute(**args),
                timeout=self._default_timeout,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(f"Tool {tool_name} completed in {duration_ms}ms")

            return {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "success",
                "error": None,
                "result": result,
                "duration_ms": duration_ms,
            }

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tool {tool_name} timed out after {self._default_timeout}s")
            return {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "timeout",
                "error": f"工具执行超时（{self._default_timeout}秒）",
                "result": None,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Tool {tool_name} failed: {e}")
            return {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "failed",
                "error": str(e),
                "result": None,
                "duration_ms": duration_ms,
            }

    async def _execute_delegate_stream(
        self,
        tool: Any,
        args: dict,
        tool_call_id: str,
        *,
        writer: StreamWriter,
        start_time: float,
    ) -> dict:
        """流式执行 delegate 工具

        通过 astream_execute() 逐步获取子智能体事件，
        每个事件通过 writer() 推送到父图的 custom 流，
        前端通过 astream_run() 的 custom 事件统一接收。

        Args:
            tool: delegate 工具实例
            args: 工具参数（role, task）
            tool_call_id: 工具调用 ID
            writer: LangGraph StreamWriter
            start_time: 开始时间

        Returns:
            dict: 最终执行结果
        """
        final_result = None
        async for sub_event in tool.astream_execute(**args):
            if not isinstance(sub_event, dict):
                continue
            event_dict = {k: v for k, v in sub_event.items() if v is not None}

            event_type = event_dict.get("type", "")
            if event_type == "answer":
                content = event_dict.get("content", "")
                if content:
                    final_result = {
                        "agent_id": args.get("role", ""),
                        "agent_name": event_dict.get("agent", ""),
                        "status": "success",
                        "result": content,
                    }

            writer(event_dict)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Tool delegate (streaming) completed in {duration_ms}ms")

        if final_result is None:
            final_result = {
                "agent_id": args.get("role", ""),
                "status": "success",
                "result": "子智能体执行完成（无明确答案）",
            }

        return {
            "tool_call_id": tool_call_id,
            "tool_name": "delegate",
            "status": "success",
            "error": None,
            "result": final_result,
            "duration_ms": duration_ms,
        }

    def _get_allowed_tools(self) -> list:
        """获取当前智能体允许使用的工具列表"""
        all_tools = self._tool_registry.get_active_tools()
        if not self._tool_names:
            return all_tools
        return [t for t in all_tools if t.name in self._tool_names]

    def _fuzzy_match_tool(self, name: str) -> Optional[Any]:
        """模糊匹配工具名称

        处理 LLM 工具名称幻觉：
        - get_current_time → current_time
        - search_web → web_search
        - calculate → code_executor

        匹配策略：去掉常见前缀（get_, run_, call_）后子串匹配

        Args:
            name: LLM 输出的工具名称

        Returns:
            匹配到的工具实例，未匹配返回 None
        """
        allowed_tools = self._get_allowed_tools()
        tool_names = [t.name for t in allowed_tools]

        if name in tool_names:
            return self._tool_registry.get(name)

        cleaned = name.lower().replace("_", "")
        for prefix in ("get", "run", "call", "fetch", "do", "use"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]

        for tool in allowed_tools:
            tool_clean = tool.name.lower().replace("_", "")
            if tool_clean in cleaned or cleaned in tool_clean:
                return tool

        return None

    @staticmethod
    def _format_observations(observations: list[dict]) -> str:
        """格式化多个工具执行结果为文本

        Args:
            observations: 执行结果列表

        Returns:
            str: 格式化后的观察结果
        """
        parts = []
        for obs in observations:
            tool_name = obs.get("tool_name", "unknown")
            status = obs.get("status", "unknown")

            parts.append(f"[{tool_name}] 状态: {status}")

            if status == "success":
                result = obs.get("result")
                if isinstance(result, (dict, list)):
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)
                else:
                    result_str = str(result)
                parts.append(f"结果:\n{result_str[:1000]}")
            else:
                error = obs.get("error", "未知错误")
                parts.append(f"错误: {error}")

            duration = obs.get("duration_ms", 0)
            parts.append(f"耗时: {duration}ms\n")

        return "\n".join(parts)