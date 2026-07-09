"""CFA-Agent 智能体管理 API

Agent 配置从 agents.yaml 加载，支持动态注册/注销。
新增 Agent 只需在配置文件添加即可，无需修改代码。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.agents.config import AgentConfig
from src.agents.service import get_agent_service
from src.api.schemas.agent import (
    AgentConfigUpdateRequest,
    AgentListResponse,
    AgentResponse,
)
from src.api.schemas.response import ApiResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=ApiResponse[AgentListResponse])
async def list_agents():
    """获取所有 Agent 配置列表"""
    agent_service = get_agent_service()
    agents = agent_service.list_all()

    agent_responses = [
        AgentResponse(
            id=config.id,
            name=config.name,
            role=config.id,
            status="active",
            config={
                "enable_verify": config.enable_verify,
                "is_entry_point": config.is_entry_point,
                "max_steps": config.max_steps,
                "tools": config.tools,
            },
            performance_metrics=None,
            last_heartbeat=None,
            created_at=None,
            is_system=True,
        )
        for config in agents
    ]

    return ApiResponse(
        success=True,
        data=AgentListResponse(agents=agent_responses, total=len(agent_responses)),
    )


@router.get("/{agent_id}", response_model=ApiResponse[AgentResponse])
async def get_agent(agent_id: str):
    """获取 Agent 配置详情"""
    agent_service = get_agent_service()
    config = agent_service.get(agent_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return ApiResponse(
        success=True,
        data=AgentResponse(
            id=config.id,
            name=config.name,
            role=config.id,
            status="active",
            config={
                "enable_verify": config.enable_verify,
                "is_entry_point": config.is_entry_point,
                "max_steps": config.max_steps,
                "max_verify_retries": config.max_verify_retries,
                "default_timeout": config.default_timeout,
                "tools": config.tools,
                "system_prompt_length": len(config.system_prompt),
                "think_prompt_length": len(config.think_prompt),
            },
            performance_metrics=None,
            last_heartbeat=None,
            created_at=None,
            is_system=True,
        ),
    )