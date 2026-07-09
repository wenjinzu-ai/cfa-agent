"""CFA-Agent MCP 集成

MCP (Model Context Protocol) 双向集成：
- MCP Client：连接外部 MCP Server，获取工具能力
- MCP Server：将 CFA-Agent 能力暴露给外部系统
"""
from src.mcp.client import MCPClientManager, MCPToolWrapper, register_mcp_tools
from src.mcp.config import MCPConfigManager
from src.mcp.server import MCPServerExposer
from src.mcp.bridge import MCPBridge, initialize_mcp_integration

__all__ = [
    "MCPClientManager",
    "MCPToolWrapper",
    "register_mcp_tools",
    "MCPConfigManager",
    "MCPServerExposer",
    "MCPBridge",
    "initialize_mcp_integration",
]