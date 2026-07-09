"""CFA-Agent 工具管理 API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.schemas.response import ApiResponse
from src.common.exceptions import ToolNotFoundError
from src.tools.registry import get_tool_registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools():
    """获取工具列表"""
    registry = get_tool_registry()
    tools = registry.list_all()
    return ApiResponse(
        success=True,
        data=[t.to_dict() for t in tools],
    )


@router.get("/{tool_name}")
async def get_tool(tool_name: str):
    """获取工具详情"""
    registry = get_tool_registry()
    try:
        tool = registry.get(tool_name)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return ApiResponse(success=True, data=tool.to_dict())


@router.get("/schemas/functions")
async def get_function_schemas():
    """获取所有工具的 OpenAI Function Calling Schema"""
    registry = get_tool_registry()
    schemas = registry.get_openai_schemas()
    return ApiResponse(success=True, data=schemas)