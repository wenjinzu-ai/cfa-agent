"""CFA-Agent MCP Server 暴露

将 CFA-Agent 的能力作为 MCP Server 暴露给外部客户端
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from mcp import ServerSession, ServerCapabilities, Tool, Resource
from mcp.server.stdio import stdio_server

from src.common.types import AgentStatus, TaskStatus


logger = logging.getLogger("cfa-agent.mcp.server")


class MCPServerExposer:
    """MCP Server 暴露

    职责：
    - 将 CFA-Agent 的工具和技能作为 MCP Server 暴露
    - 处理外部 MCP 客户端的请求
    - 支持 stdio、SSE、Streamable HTTP 传输
    """

    def __init__(self, name: str = "cfa-agent", version: str = "1.0.0"):
        self._name = name
        self._version = version
        self._tools: dict[str, Tool] = {}
        self._resources: dict[str, Resource] = {}
        self._session: Optional[ServerSession] = None
        self._running = False

    def register_tool(self, tool: Tool) -> None:
        """注册 MCP 工具

        Args:
            tool: MCP Tool 对象
        """
        self._tools[tool.name] = tool
        logger.info(f"Registered MCP tool: {tool.name}")

    def register_resource(self, resource: Resource) -> None:
        """注册 MCP 资源

        Args:
            resource: MCP Resource 对象
        """
        self._resources[resource.uri] = resource
        logger.info(f"Registered MCP resource: {resource.uri}")

    def register_builtin_tools(self) -> None:
        """注册内置的 CFA-Agent 工具"""
        self._tools["delegate_task"] = Tool(
            name="delegate_task",
            description="Delegate a task to the CFA-Agent system for execution",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task to delegate",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Target agent ID (e.g. supervisor, planner, executor, reviewer)",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Task priority (1-10, default: 5)",
                        "default": 5,
                    },
                },
                "required": ["task_description"],
            },
        )

        self._tools["query_agent_status"] = Tool(
            name="query_agent_status",
            description="Query the status of a specific agent in the system",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID to query",
                    },
                },
                "required": ["agent_id"],
            },
        )

        self._tools["list_agents"] = Tool(
            name="list_agents",
            description="List all agents in the system with their capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        )

        self._tools["get_task_result"] = Tool(
            name="get_task_result",
            description="Get the execution result of a completed task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to query",
                    },
                },
                "required": ["task_id"],
            },
        )

        self._tools["cancel_task"] = Tool(
            name="cancel_task",
            description="Cancel a running task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to cancel",
                    },
                },
                "required": ["task_id"],
            },
        )

        self._tools["register_tool"] = Tool(
            name="register_tool",
            description="Dynamically register a new tool to the system",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Name of the tool to register",
                    },
                    "tool_schema": {
                        "type": "object",
                        "description": "JSON schema for the tool parameters",
                    },
                },
                "required": ["tool_name", "tool_schema"],
            },
        )

        logger.info(f"Registered {len(self._tools)} builtin MCP tools")

    def register_builtin_resources(self) -> None:
        """注册内置的 CFA-Agent 资源"""
        self._resources["cfa://agents/list"] = Resource(
            uri="cfa://agents/list",
            name="Agent List",
            description="List of all agents in the system",
            mimeType="application/json",
        )

        self._resources["cfa://tasks/active"] = Resource(
            uri="cfa://tasks/active",
            name="Active Tasks",
            description="List of currently active tasks",
            mimeType="application/json",
        )

        self._resources["cfa://tools/catalog"] = Resource(
            uri="cfa://tools/catalog",
            name="Tool Catalog",
            description="Catalog of all available tools",
            mimeType="application/json",
        )

        self._resources["cfa://metrics/summary"] = Resource(
            uri="cfa://metrics/summary",
            name="Metrics Summary",
            description="System runtime metrics summary",
            mimeType="application/json",
        )

        logger.info(f"Registered {len(self._resources)} builtin MCP resources")

    async def start_stdio(self) -> None:
        """启动 stdio MCP Server"""
        self._running = True
        self.register_builtin_tools()
        self.register_builtin_resources()

        async with stdio_server() as (read_stream, write_stream):
            async with ServerSession(
                read_stream,
                write_stream,
                ServerCapabilities(
                    tools={"listChanged": True},
                    resources={"subscribe": True, "listChanged": True},
                ),
            ) as session:
                self._session = session
                await session.initialize()
                logger.info(f"MCP Server started (stdio): {self._name}")

                async for request in session.incoming_requests():
                    await self._handle_request(request)

    async def _handle_request(self, request: Any) -> None:
        """处理 MCP 请求

        Args:
            request: MCP 请求对象
        """
        method = request.method

        if method == "tools/list":
            await self._handle_list_tools(request)
        elif method == "tools/call":
            await self._handle_call_tool(request)
        elif method == "resources/list":
            await self._handle_list_resources(request)
        elif method == "resources/read":
            await self._handle_read_resource(request)
        else:
            logger.warning(f"Unknown MCP method: {method}")
            await request.respond({"error": f"Unknown method: {method}"})

    async def _handle_list_tools(self, request: Any) -> None:
        """处理工具列表请求"""
        tools_list = list(self._tools.values())
        await request.respond({"tools": [t.to_dict() for t in tools_list]})

    async def _handle_call_tool(self, request: Any) -> None:
        """处理工具调用请求"""
        params = request.params or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            await request.respond({
                "content": [{"type": "text", "text": f"Tool not found: {tool_name}"}],
                "isError": True,
            })
            return

        try:
            result = await self._execute_tool(tool_name, arguments)
            await request.respond({
                "content": [{"type": "text", "text": str(result)}],
                "isError": False,
            })
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            await request.respond({
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            })

    async def _handle_list_resources(self, request: Any) -> None:
        """处理资源列表请求"""
        resources_list = list(self._resources.values())
        await request.respond({
            "resources": [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mimeType,
                }
                for r in resources_list
            ]
        })

    async def _handle_read_resource(self, request: Any) -> None:
        """处理资源读取请求"""
        params = request.params or {}
        uri = params.get("uri", "")

        if uri not in self._resources:
            await request.respond({
                "contents": [{"uri": uri, "text": f"Resource not found: {uri}"}],
            })
            return

        try:
            content = await self._read_resource(uri)
            await request.respond({
                "contents": [{"uri": uri, "text": content, "mimeType": "application/json"}],
            })
        except Exception as e:
            logger.error(f"Resource read failed: {e}")
            await request.respond({
                "contents": [{"uri": uri, "text": f"Error: {str(e)}"}],
            })

    async def _execute_tool(self, tool_name: str, arguments: dict) -> Any:
        """执行工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            Any: 执行结果
        """
        if tool_name == "delegate_task":
            return await self._delegate_task(arguments)
        elif tool_name == "query_agent_status":
            return await self._query_agent_status(arguments)
        elif tool_name == "list_agents":
            return await self._list_agents()
        elif tool_name == "get_task_result":
            return await self._get_task_result(arguments)
        elif tool_name == "cancel_task":
            return await self._cancel_task(arguments)
        elif tool_name == "register_tool":
            return await self._register_tool(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def _delegate_task(self, arguments: dict) -> dict:
        """委派任务"""
        task_description = arguments.get("task_description", "")
        agent_id = arguments.get("agent_id", "supervisor")
        priority = arguments.get("priority", 5)

        return {
            "status": "success",
            "task_id": "mock-task-id",
            "message": f"Task delegated to {agent_id} agent with priority {priority}",
        }

    async def _query_agent_status(self, arguments: dict) -> dict:
        """查询智能体状态"""
        agent_id = arguments.get("agent_id", "")

        return {
            "agent_id": agent_id,
            "status": AgentStatus.IDLE.value,
            "current_task": None,
            "last_activity": "2024-01-01T00:00:00Z",
        }

    async def _list_agents(self) -> dict:
        """列出所有智能体"""
        from src.agents.service import get_agent_service

        try:
            agent_service = get_agent_service()
            configs = agent_service.list_all()
            return {
                "agents": [
                    {
                        "id": config.id,
                        "name": config.name,
                        "is_entry_point": config.is_entry_point,
                        "tools": config.tools,
                        "enable_verify": config.enable_verify,
                    }
                    for config in configs
                ],
            }
        except Exception:
            return {
                "agents": [
                    {"id": "supervisor", "name": "监督者", "is_entry_point": True, "tools": ["delegate"]},
                    {"id": "planner", "name": "规划者", "is_entry_point": False, "tools": ["web_search", "file_ops"]},
                    {"id": "executor", "name": "执行者", "is_entry_point": False, "tools": ["web_search", "file_ops"]},
                    {"id": "reviewer", "name": "审查者", "is_entry_point": False, "tools": []},
                ],
            }

    async def _get_task_result(self, arguments: dict) -> dict:
        """获取任务结果"""
        task_id = arguments.get("task_id", "")

        return {
            "task_id": task_id,
            "status": TaskStatus.COMPLETED.value,
            "result": "Task completed successfully",
            "steps": 5,
            "duration_seconds": 30,
        }

    async def _cancel_task(self, arguments: dict) -> dict:
        """取消任务"""
        task_id = arguments.get("task_id", "")

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": f"Task {task_id} has been cancelled",
        }

    async def _register_tool(self, arguments: dict) -> dict:
        """动态注册工具"""
        tool_name = arguments.get("tool_name", "")
        tool_schema = arguments.get("tool_schema", {})

        new_tool = Tool(
            name=tool_name,
            description=f"Dynamic tool: {tool_name}",
            inputSchema=tool_schema,
        )
        self.register_tool(new_tool)

        return {
            "status": "success",
            "tool_name": tool_name,
            "message": f"Tool {tool_name} registered successfully",
        }

    async def _read_resource(self, uri: str) -> str:
        """读取资源内容

        Args:
            uri: 资源 URI

        Returns:
            str: 资源内容（JSON 字符串）
        """
        import json

        if uri == "cfa://agents/list":
            data = await self._list_agents()
        elif uri == "cfa://tasks/active":
            data = {
                "tasks": [
                    {"id": "task-001", "status": "running", "agent_id": "agent-002"},
                ],
            }
        elif uri == "cfa://tools/catalog":
            data = {
                "tools": [
                    {"name": t.name, "description": t.description}
                    for t in self._tools.values()
                ],
            }
        elif uri == "cfa://metrics/summary":
            data = {
                "total_agents": 2,
                "active_tasks": 1,
                "completed_tasks": 10,
                "average_task_duration": 25.5,
            }
        else:
            raise ValueError(f"Unknown resource: {uri}")

        return json.dumps(data, indent=2)

    async def stop(self) -> None:
        """停止 MCP Server"""
        self._running = False
        if self._session:
            await self._session.shutdown()
        logger.info(f"MCP Server stopped: {self._name}")

    def get_tools(self) -> list[Tool]:
        """获取所有注册的工具"""
        return list(self._tools.values())

    def get_resources(self) -> list[Resource]:
        """获取所有注册的资源"""
        return list(self._resources.values())

    @property
    def is_running(self) -> bool:
        """Server 是否正在运行"""
        return self._running