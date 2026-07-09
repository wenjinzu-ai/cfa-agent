"""CFA-Agent 智能体相关 Schema"""
from __future__ import annotations


from pydantic import BaseModel, Field


class AgentConfigUpdateRequest(BaseModel):
    """配置更新请求 — 扩展系统智能体的能力"""
    config: dict = Field(..., description="配置项: tools, skills, prompts, model_params 等")


class AgentResponse(BaseModel):
    """智能体响应"""
    id: str
    name: str
    role: str
    status: str
    config: dict | None = None
    performance_metrics: dict | None = None
    last_heartbeat: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    is_system: bool = False


class AgentListResponse(BaseModel):
    """智能体列表响应"""
    agents: list[AgentResponse]
    total: int


class AgentToolBindingRequest(BaseModel):
    """工具绑定请求"""
    tool_name: str = Field(..., description="工具名称")
    tool_source: str = Field("builtin", description="工具来源: builtin/mcp")
    proficiency: float = Field(0.5, ge=0, le=1, description="熟练度")


class AgentToolBindingResponse(BaseModel):
    """工具绑定响应"""
    agent_id: str
    tool_name: str
    tool_source: str
    proficiency: float