"""CFA-Agent 任务相关 Schema"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.common.types import ExecutionMode


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    description: str = Field(..., min_length=1, description="任务描述")
    session_id: str | None = Field(None, description="会话 ID")
    mode: ExecutionMode = Field(ExecutionMode.SYNC, description="执行模式: sync(SSE流式)/async(轮询)")
    priority: int = Field(0, ge=0, le=10, description="优先级")
    max_iterations: int = Field(20, ge=1, le=100, description="最大迭代次数")


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    parent_task_id: str | None = None
    session_id: str | None = None
    conversation_index: int = 0
    mode: str
    description: str
    status: str
    introspection_state: str | None = None
    priority: int = 0
    assigned_agent_id: str | None = None
    result: dict | None = None
    iteration_count: int = 0
    max_iterations: int = 20
    waiting_question: str | None = None
    created_at: str
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: list[TaskResponse]
    total: int


class TaskCancelRequest(BaseModel):
    """取消任务请求"""
    reason: str | None = Field(None, description="取消原因")


class TaskAnswerRequest(BaseModel):
    """回答用户问题请求（用于 waiting_user 状态的任务）"""
    answer: str = Field(..., min_length=1, description="用户回答")