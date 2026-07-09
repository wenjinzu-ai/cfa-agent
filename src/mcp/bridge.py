"""CFA-Agent LangChain MCP 适配桥接

将 MCP 工具适配为 LangChain/LangGraph 可调用的 Tool 格式
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.tools.base import BaseTool
from src.tools.registry import get_tool_registry
from src.common.types import ToolSource


logger = logging.getLogger("cfa-agent.mcp.bridge")


class MCPBridge:
    """MCP 适配桥接

    职责：
    - 将 MCP 工具转换为 BaseTool 实例
    - 透明化 MCP 工具与内置工具的差异
    - 供 ToolRegistry 统一管理
    """

    def __init__(self):
        self._registry = get_tool_registry()

    async def adapt_tool(
        self,
        server_name: str,
        tool_info: dict,
        client_manager: Any,
    ) -> BaseTool:
        """将 MCP 工具适配为 BaseTool 实例

        Args:
            server_name: MCP Server 名称
            tool_info: 工具信息（name, description, input_schema）
            client_manager: MCP Client 管理器

        Returns:
            BaseTool: 适配后的工具实例
        """
        from src.mcp.client import MCPToolWrapper

        wrapper = MCPToolWrapper(
            server_name=server_name,
            tool_info=tool_info,
            client_manager=client_manager,
        )

        logger.info(f"Adapted MCP tool: {tool_info['name']} from {server_name}")
        return wrapper

    async def adapt_all_tools(
        self,
        server_name: str,
        tools: list[dict],
        client_manager: Any,
    ) -> list[BaseTool]:
        """将 MCP Server 的所有工具适配为 BaseTool 实例

        Args:
            server_name: MCP Server 名称
            tools: 工具信息列表
            client_manager: MCP Client 管理器

        Returns:
            list[BaseTool]: 适配后的工具列表
        """
        adapted_tools = []
        for tool_info in tools:
            tool = await self.adapt_tool(server_name, tool_info, client_manager)
            adapted_tools.append(tool)

        logger.info(f"Adapted {len(adapted_tools)} tools from {server_name}")
        return adapted_tools

    async def register_to_registry(
        self,
        server_name: str,
        tools: list[dict],
        client_manager: Any,
    ) -> int:
        """将 MCP 工具注册到 ToolRegistry

        Args:
            server_name: MCP Server 名称
            tools: 工具信息列表
            client_manager: MCP Client 管理器

        Returns:
            int: 注册的工具数量
        """
        adapted_tools = await self.adapt_all_tools(
            server_name, tools, client_manager
        )

        count = 0
        for tool in adapted_tools:
            self._registry.register(tool)
            count += 1

        logger.info(f"Registered {count} MCP tools to ToolRegistry")
        return count

    def unregister_from_registry(self, server_name: str) -> int:
        """从 ToolRegistry 移除指定 Server 的所有工具

        Args:
            server_name: MCP Server 名称

        Returns:
            int: 移除的工具数量
        """
        mcp_tools = self._registry.get_tools_by_source(ToolSource.MCP)
        count = 0

        for tool in mcp_tools:
            if hasattr(tool, "_server_name") and tool._server_name == server_name:
                self._registry.unregister(tool.name)
                count += 1

        logger.info(f"Unregistered {count} MCP tools from {server_name}")
        return count

    def get_mcp_tools(self) -> list[BaseTool]:
        """获取所有 MCP 工具

        Returns:
            list[BaseTool]: MCP 工具列表
        """
        return self._registry.get_tools_by_source(ToolSource.MCP)

    def get_tools_by_server(self, server_name: str) -> list[BaseTool]:
        """获取指定 Server 的 MCP 工具

        Args:
            server_name: MCP Server 名称

        Returns:
            list[BaseTool]: 工具列表
        """
        mcp_tools = self.get_mcp_tools()
        return [
            t for t in mcp_tools
            if hasattr(t, "_server_name") and t._server_name == server_name
        ]


async def initialize_mcp_integration(
    client_manager: Any,
    config_manager: Any,
    bridge: MCPBridge,
) -> int:
    """初始化 MCP 集成

    加载配置、连接 Server、发现工具并注册到 ToolRegistry

    Args:
        client_manager: MCP Client 管理器
        config_manager: MCP 配置管理器
        bridge: MCP 桥接器

    Returns:
        int: 注册的工具总数
    """
    servers = await config_manager.merge_configs()
    total_tools = 0

    for server in servers:
        if not server.get("enabled", True):
            continue

        if not config_manager.validate_config(server):
            logger.warning(f"Skipping invalid server config: {server['name']}")
            continue

        try:
            status = await client_manager.connect_server(
                server["name"],
                server["transport"],
                server["config"],
            )

            if status.value != "connected":
                logger.warning(f"Failed to connect to {server['name']}")
                continue

            tools = await client_manager.discover_tools(server["name"])
            count = await bridge.register_to_registry(
                server["name"], tools, client_manager
            )
            total_tools += count

        except Exception as e:
            logger.error(f"Failed to initialize MCP server {server['name']}: {e}")

    logger.info(f"MCP integration initialized: {total_tools} tools registered")
    return total_tools