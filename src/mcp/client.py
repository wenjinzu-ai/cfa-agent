"""CFA-Agent MCP Client 管理器

管理与 MCP Server 的连接，发现和调用 MCP 工具
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client

from src.common.types import MCPStatus, MCPTransport, ToolSource
from src.db.repository.mcp_repo import MCPRepository
from src.tools.base import BaseTool
from src.tools.registry import get_tool_registry


logger = logging.getLogger("cfa-agent.mcp.client")


class MCPClientManager:
    """MCP Client 管理器

    职责：
    - 管理 MCP Server 连接（支持 stdio、SSE、Streamable HTTP）
    - 发现 MCP 工具并缓存到数据库
    - 调用 MCP 工具
    - 维护连接状态和健康检查
    - 自动重连机制
    """

    def __init__(self, repo: Optional[MCPRepository] = None):
        self._repo = repo
        self._sessions: dict[str, ClientSession] = {}
        self._server_configs: dict[str, dict] = {}
        self._tool_registry = get_tool_registry()
        self._health_check_interval = 60
        self._max_reconnect_attempts = 3
        self._reconnect_delay = 5

    async def connect_server(
        self,
        name: str,
        transport: MCPTransport,
        config: dict,
    ) -> MCPStatus:
        """连接 MCP Server

        Args:
            name: Server 名称
            transport: 传输协议类型
            config: 连接配置

        Returns:
            MCPStatus: 连接状态
        """
        if name in self._sessions:
            logger.warning(f"Server {name} already connected")
            return MCPStatus.CONNECTED

        self._server_configs[name] = {
            "transport": transport,
            "config": config,
        }

        try:
            if transport == MCPTransport.STDIO:
                session = await self._connect_stdio(name, config)
            elif transport == MCPTransport.SSE:
                session = await self._connect_sse(name, config)
            elif transport == MCPTransport.STREAMABLE_HTTP:
                session = await self._connect_streamable_http(name, config)
            else:
                raise ValueError(f"Unsupported transport: {transport}")

            self._sessions[name] = session

            if self._repo:
                await self._repo.update_status(name, MCPStatus.CONNECTED)

            logger.info(f"Connected to MCP Server: {name}")
            return MCPStatus.CONNECTED

        except Exception as e:
            logger.error(f"Failed to connect to {name}: {e}")
            if self._repo:
                await self._repo.update_status(name, MCPStatus.ERROR)
            return MCPStatus.ERROR

    async def _connect_stdio(self, name: str, config: dict) -> ClientSession:
        """通过 stdio 连接 MCP Server

        Args:
            name: Server 名称
            config: 连接配置，包含 command、args、env

        Returns:
            ClientSession: MCP 会话
        """
        command = config.get("command", "")
        args = config.get("args", [])
        env = config.get("env", {})

        if not command:
            raise ValueError("stdio transport requires 'command' in config")

        full_env = os.environ.copy()
        full_env.update(env)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=full_env,
        )

        read_stream, write_stream = await stdio_client(server_params)

        session = ClientSession(read_stream, write_stream)
        await session.initialize()

        return session

    async def _connect_sse(self, name: str, config: dict) -> ClientSession:
        """通过 SSE 连接 MCP Server

        Args:
            name: Server 名称
            config: 连接配置，包含 url

        Returns:
            ClientSession: MCP 会话
        """
        url = config.get("url", "")
        if not url:
            raise ValueError("SSE transport requires 'url' in config")

        from mcp.client.sse import sse_client

        read_stream, write_stream = await sse_client(url)

        session = ClientSession(read_stream, write_stream)
        await session.initialize()

        return session

    async def _connect_streamable_http(
        self, name: str, config: dict
    ) -> ClientSession:
        """通过 Streamable HTTP 连接 MCP Server

        Args:
            name: Server 名称
            config: 连接配置，包含 url

        Returns:
            ClientSession: MCP 会话
        """
        url = config.get("url", "")
        if not url:
            raise ValueError("Streamable HTTP transport requires 'url' in config")

        from mcp.client.streamable_http import streamablehttp_client

        read_stream, write_stream, _ = await streamablehttp_client(url)

        session = ClientSession(read_stream, write_stream)
        await session.initialize()

        return session

    async def disconnect_server(self, name: str) -> None:
        """断开 MCP Server 连接

        Args:
            name: Server 名称
        """
        if name not in self._sessions:
            return

        session = self._sessions[name]
        try:
            await session.send_notification({"method": "shutdown"})
        except Exception as e:
            logger.warning(f"Error sending shutdown to {name}: {e}")

        del self._sessions[name]
        del self._server_configs[name]

        if self._repo:
            await self._repo.update_status(name, MCPStatus.DISCONNECTED)

        logger.info(f"Disconnected from MCP Server: {name}")

    async def discover_tools(self, server_name: str) -> list[dict]:
        """发现 MCP Server 提供的工具

        Args:
            server_name: Server 名称

        Returns:
            list[dict]: 工具列表
        """
        if server_name not in self._sessions:
            logger.error(f"Server {server_name} not connected")
            return []

        session = self._sessions[server_name]
        try:
            result = await session.list_tools()
            tools = []

            for tool in result.tools:
                tool_info = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema or {},
                }
                tools.append(tool_info)

                if self._repo:
                    server = await self._repo.get_server_by_name(server_name)
                    if server:
                        await self._repo.cache_tool(
                            server_id=server["id"],
                            tool_name=tool.name,
                            tool_schema=tool_info,
                        )

            logger.info(f"Discovered {len(tools)} tools from {server_name}")
            return tools

        except Exception as e:
            logger.error(f"Failed to discover tools from {server_name}: {e}")
            return []

    async def discover_all_tools(self) -> dict[str, list[dict]]:
        """发现所有已连接 Server 的工具

        Returns:
            dict[str, list[dict]]: Server 名称 -> 工具列表
        """
        all_tools = {}
        for server_name in self._sessions:
            tools = await self.discover_tools(server_name)
            all_tools[server_name] = tools
        return all_tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
    ) -> Any:
        """调用 MCP 工具

        Args:
            server_name: Server 名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            Any: 工具执行结果
        """
        if server_name not in self._sessions:
            raise ValueError(f"Server {server_name} not connected")

        session = self._sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments=arguments)

            content_blocks = []
            for content in result.content:
                if hasattr(content, "text"):
                    content_blocks.append(content.text)
                elif hasattr(content, "data"):
                    content_blocks.append(content.data)
                else:
                    content_blocks.append(str(content))

            return {
                "status": "success",
                "content": content_blocks,
                "is_error": result.isError if hasattr(result, "isError") else False,
            }

        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_name}: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_server_status(self, name: str) -> MCPStatus:
        """获取 MCP Server 状态

        Args:
            name: Server 名称

        Returns:
            MCPStatus: Server 状态
        """
        if name not in self._sessions:
            if self._repo:
                server = await self._repo.get_server_by_name(name)
                if server:
                    return MCPStatus(server["status"])
            return MCPStatus.DISCONNECTED

        try:
            session = self._sessions[name]
            await session.send_ping()
            return MCPStatus.CONNECTED
        except Exception:
            return MCPStatus.ERROR

    async def health_check_all(self) -> dict[str, MCPStatus]:
        """对所有 Server 进行健康检查

        Returns:
            dict[str, MCPStatus]: Server 名称 -> 状态
        """
        statuses = {}
        for name in list(self._sessions.keys()):
            status = await self.get_server_status(name)
            statuses[name] = status

            if status == MCPStatus.ERROR:
                logger.warning(f"Server {name} health check failed, attempting reconnect")
                await self._attempt_reconnect(name)

        return statuses

    async def _attempt_reconnect(self, name: str) -> bool:
        """尝试重新连接 Server

        Args:
            name: Server 名称

        Returns:
            bool: 是否成功重连
        """
        if name not in self._server_configs:
            return False

        config = self._server_configs[name]
        transport = config["transport"]

        for attempt in range(self._max_reconnect_attempts):
            try:
                logger.info(f"Reconnecting to {name} (attempt {attempt + 1})")
                await asyncio.sleep(self._reconnect_delay * (attempt + 1))

                status = await self.connect_server(name, transport, config["config"])
                if status == MCPStatus.CONNECTED:
                    logger.info(f"Successfully reconnected to {name}")
                    return True

            except Exception as e:
                logger.error(f"Reconnect attempt {attempt + 1} failed: {e}")

        logger.error(f"Failed to reconnect to {name} after {self._max_reconnect_attempts} attempts")
        return False

    async def list_resources(self, server_name: str) -> list[dict]:
        """列出 MCP Server 的资源

        Args:
            server_name: Server 名称

        Returns:
            list[dict]: 资源列表
        """
        if server_name not in self._sessions:
            return []

        session = self._sessions[server_name]
        try:
            result = await session.list_resources()
            resources = []
            for resource in result.resources:
                resources.append({
                    "uri": resource.uri,
                    "name": resource.name or "",
                    "description": resource.description or "",
                    "mimeType": resource.mimeType or "",
                })
            return resources
        except Exception as e:
            logger.error(f"Failed to list resources from {server_name}: {e}")
            return []

    async def read_resource(self, server_name: str, uri: str) -> Any:
        """读取 MCP Server 的资源

        Args:
            server_name: Server 名称
            uri: 资源 URI

        Returns:
            Any: 资源内容
        """
        if server_name not in self._sessions:
            raise ValueError(f"Server {server_name} not connected")

        session = self._sessions[server_name]
        try:
            result = await session.read_resource(uri)
            contents = []
            for content in result.contents:
                if hasattr(content, "text"):
                    contents.append(content.text)
                elif hasattr(content, "blob"):
                    contents.append(content.blob)
                else:
                    contents.append(str(content))
            return contents
        except Exception as e:
            logger.error(f"Failed to read resource {uri} from {server_name}: {e}")
            raise

    def get_connected_servers(self) -> list[str]:
        """获取已连接的 Server 名称列表

        Returns:
            list[str]: Server 名称列表
        """
        return list(self._sessions.keys())

    @property
    def connected_count(self) -> int:
        """已连接 Server 数量"""
        return len(self._sessions)


class MCPToolWrapper(BaseTool):
    """MCP 工具包装器

    将 MCP 工具适配为 BaseTool 格式，供 ToolRegistry 统一管理
    """

    def __init__(
        self,
        server_name: str,
        tool_info: dict,
        client_manager: MCPClientManager,
    ):
        super().__init__(source=ToolSource.MCP)
        self._server_name = server_name
        self._tool_info = tool_info
        self._client_manager = client_manager

    @property
    def name(self) -> str:
        return self._tool_info.get("name", "unknown")

    @property
    def description(self) -> str:
        return self._tool_info.get("description", "")

    @property
    def parameters_schema(self) -> dict:
        return self._tool_info.get("input_schema", {
            "type": "object",
            "properties": {},
        })

    async def execute(self, **kwargs) -> Any:
        return await self._client_manager.call_tool(
            self._server_name,
            self.name,
            kwargs,
        )

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict["server_name"] = self._server_name
        return base_dict


async def register_mcp_tools(
    client_manager: MCPClientManager,
    server_name: str,
) -> int:
    """将 MCP Server 的工具注册到 ToolRegistry

    Args:
        client_manager: MCP Client 管理器
        server_name: Server 名称

    Returns:
        int: 注册的工具数量
    """
    tools = await client_manager.discover_tools(server_name)
    registry = get_tool_registry()
    count = 0

    for tool_info in tools:
        wrapper = MCPToolWrapper(server_name, tool_info, client_manager)
        registry.register(wrapper)
        count += 1
        logger.info(f"Registered MCP tool: {tool_info['name']} from {server_name}")

    return count