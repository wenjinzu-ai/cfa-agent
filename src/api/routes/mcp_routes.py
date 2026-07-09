"""CFA-Agent MCP 管理 API"""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.response import ApiResponse

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers")
async def list_mcp_servers():
    """获取 MCP Server 列表"""
    return ApiResponse(success=True, data=[])


@router.post("/servers/{server_name}/connect")
async def connect_mcp_server(server_name: str):
    """连接 MCP Server"""
    return ApiResponse(success=True, message="MCP Server connection initiated")


@router.post("/servers/{server_name}/disconnect")
async def disconnect_mcp_server(server_name: str):
    """断开 MCP Server 连接"""
    return ApiResponse(success=True, message="MCP Server disconnected")