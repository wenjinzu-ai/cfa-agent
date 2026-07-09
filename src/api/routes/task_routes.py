"""CFA-Agent 任务管理 API"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from src.api.schemas.response import ApiResponse
from src.api.schemas.task import (
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
)
from src.common.types import TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=ApiResponse[TaskResponse])
async def create_task(request: TaskCreateRequest):
    """创建任务"""
    from src.db.connection import get_db
    from src.db.repository.task_repo import TaskRepository

    db = await get_db()
    task_repo = TaskRepository(db)

    task_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    task = await task_repo.create(
        task_id=task_id,
        description=request.description,
        session_id=session_id,
        mode=request.mode,
        priority=request.priority,
        max_iterations=request.max_iterations,
    )

    return ApiResponse(
        success=True,
        message="Task created successfully",
        data=TaskResponse(
            id=task["id"],
            parent_task_id=task.get("parent_task_id"),
            session_id=task.get("session_id"),
            conversation_index=task.get("conversation_index", 0),
            mode=task.get("mode", "sync"),
            description=task["description"],
            status=task["status"],
            introspection_state=task.get("introspection_state"),
            priority=task.get("priority", 0),
            assigned_agent_id=task.get("assigned_agent_id"),
            result=task.get("result"),
            iteration_count=task.get("iteration_count", 0),
            max_iterations=task.get("max_iterations", 20),
            waiting_question=task.get("waiting_question"),
            created_at=task["created_at"],
            completed_at=task.get("completed_at"),
        ),
    )


@router.get("", response_model=ApiResponse[TaskListResponse])
async def list_tasks(status: TaskStatus | None = None, limit: int = 50):
    """获取任务列表"""
    from src.db.connection import get_db
    from src.db.repository.task_repo import TaskRepository

    db = await get_db()
    task_repo = TaskRepository(db)

    if status:
        tasks = await task_repo.get_by_status(status)
    else:
        tasks = await task_repo.list_recent(limit)

    task_responses = [
        TaskResponse(
            id=t["id"],
            parent_task_id=t.get("parent_task_id"),
            session_id=t.get("session_id"),
            conversation_index=t.get("conversation_index", 0),
            mode=t.get("mode", "sync"),
            description=t["description"],
            status=t["status"],
            introspection_state=t.get("introspection_state"),
            priority=t.get("priority", 0),
            assigned_agent_id=t.get("assigned_agent_id"),
            result=t.get("result"),
            iteration_count=t.get("iteration_count", 0),
            max_iterations=t.get("max_iterations", 20),
            waiting_question=t.get("waiting_question"),
            created_at=t["created_at"],
            completed_at=t.get("completed_at"),
        )
        for t in tasks
    ]

    return ApiResponse(
        success=True,
        data=TaskListResponse(tasks=task_responses, total=len(task_responses)),
    )


@router.get("/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(task_id: str):
    """获取任务详情"""
    from src.db.connection import get_db
    from src.db.repository.task_repo import TaskRepository

    db = await get_db()
    task_repo = TaskRepository(db)

    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return ApiResponse(
        success=True,
        data=TaskResponse(
            id=task["id"],
            parent_task_id=task.get("parent_task_id"),
            session_id=task.get("session_id"),
            conversation_index=task.get("conversation_index", 0),
            mode=task.get("mode", "sync"),
            description=task["description"],
            status=task["status"],
            introspection_state=task.get("introspection_state"),
            priority=task.get("priority", 0),
            assigned_agent_id=task.get("assigned_agent_id"),
            result=task.get("result"),
            iteration_count=task.get("iteration_count", 0),
            max_iterations=task.get("max_iterations", 20),
            waiting_question=task.get("waiting_question"),
            created_at=task["created_at"],
            completed_at=task.get("completed_at"),
        ),
    )


@router.post("/{task_id}/cancel", response_model=ApiResponse[None])
async def cancel_task(task_id: str):
    """取消任务"""
    from src.db.connection import get_db
    from src.db.repository.task_repo import TaskRepository

    db = await get_db()
    task_repo = TaskRepository(db)

    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    await task_repo.update_status(task_id, TaskStatus.CANCELLED)
    return ApiResponse(success=True, message="Task cancelled successfully")