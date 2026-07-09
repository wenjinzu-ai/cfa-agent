"""Chat 统一路由 - 实时流式输出

统一入口：POST /chat/stream
  所有请求走 Supervisor，简单问题直接回答，复杂任务自动委派专家智能体

实时流式架构（业界标准 Supervisor + Worker 模式）：
  使用 LangGraph astream(stream_mode=["updates","custom"]) 逐步推送事件
  - 每个节点执行后立即推送 SSE 事件（不再等全部完成）
  - delegate 工具内子智能体也通过 astream_execute 实时推送
  - 思考过程实时可见，工具调用即时反馈
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agents.config import AgentConfig
from src.agents.service import get_agent_service
from src.api.schemas.response import ApiResponse
from src.common.types import TaskStatus
from src.db.connection import get_db
from src.db.repository.memory_repo import MemoryRepository
from src.db.repository.task_repo import TaskRepository
from src.llm.adapter import LLMAdapter
from src.llm.router import LLMRouter
from src.llm.token_counter import TokenCounter
from src.loop_engine.graph import ReActGraph
from src.memory.manager import MemoryManager
from src.skills.registry import SkillRegistry
from src.tools.builtin.delegate import Delegate
from src.tools.registry import get_tool_registry

logger = logging.getLogger("cfa-agent.chat")

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatStreamRequest(BaseModel):
    message: str = Field(..., description="用户消息", min_length=1)
    session_id: str | None = Field(None, description="会话 ID，不传则创建新会话")
    agent_id: str = Field(default="supervisor", description="Agent ID，默认 Supervisor")
    max_steps: int = Field(default=10, ge=1, le=50)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=8192)


def _get_agent_config(agent_id: str) -> AgentConfig:
    agent_service = get_agent_service()
    if agent_service.size == 0:
        raise HTTPException(status_code=500, detail="AgentService 未初始化")
    config = agent_service.get(agent_id)
    if config is None:
        available = ", ".join(agent_service.list_ids())
        raise HTTPException(status_code=400, detail=f"Agent 不存在: {agent_id}，可用: {available}")
    return config


def _sse(data: dict | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_execute(
    task: str,
    agent_config: AgentConfig,
    max_steps: int,
    temperature: float,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """实时流式执行 - 业界标准 Supervisor + Worker 模式

    核心改造：
    - 使用 graph.astream_run() 替代 graph.run()
    - 每个节点执行后立即 yield SSE 事件
    - delegate 工具调用时，拦截并使用 astream_execute 实时推送子智能体事件
    - 思考过程、工具调用、观察结果全部实时可见
    - 会话内记忆：从DB加载历史对话注入context
    """
    stream_id = str(uuid.uuid4())

    if session_id is None:
        session_id = str(uuid.uuid4())
        try:
            await _create_session(session_id, summary=task[:50])
        except Exception:
            pass

    try:
        await _append_session_history(session_id, {"role": "user", "content": task})
    except Exception:
        pass

    conversation_history = await _load_session_history(session_id)

    yield _sse({"type": "start", "stream_id": stream_id, "session_id": session_id, "agent_id": agent_config.id, "agent_name": agent_config.name})

    adapter = LLMAdapter()
    llm_router = LLMRouter(adapter=adapter)
    tool_registry = get_tool_registry()
    token_counter = TokenCounter()

    if agent_config.is_entry_point:
        delegate = tool_registry.get("delegate") if "delegate" in [t.name for t in tool_registry.list_all()] else Delegate(max_steps=max_steps)
        skill_registry_for_delegate = await _get_skill_registry()
        agent_service_instance = get_agent_service()
        delegate.init_runtime_deps(router=llm_router, token_counter=token_counter, skill_registry=skill_registry_for_delegate, agent_service=agent_service_instance)
        if "delegate" not in [t.name for t in tool_registry.list_all()]:
            tool_registry.register(delegate)

    memory = await _get_memory_manager()
    skill_registry = await _get_skill_registry()

    graph = ReActGraph.create(
        router=llm_router,
        tool_registry=tool_registry,
        token_counter=token_counter,
        agent_config=agent_config,
        memory=memory,
        skill_registry=skill_registry,
        agent_service=get_agent_service(),
    )

    start_time = time.time()
    step_count = 0
    has_delegation = False
    task_id = None
    final_answer = ""

    try:
        context = {"conversation_history": conversation_history} if conversation_history else {}
        event_queue: asyncio.Queue = asyncio.Queue()
        stream_done = False

        async def _consume_stream():
            nonlocal stream_done
            try:
                async for event in graph.astream_run(task=task, context=context, max_steps=agent_config.max_steps):
                    await event_queue.put(event)
            except Exception as e:
                await event_queue.put({"type": "error", "content": str(e)})
            finally:
                stream_done = True
                await event_queue.put(None)

        consumer_task = asyncio.create_task(_consume_stream())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield _sse({"type": "heartbeat", "timestamp": int(time.time())})
                    continue

                if event is None:
                    break
                if not isinstance(event, dict):
                    continue

                event_type = event.get("type", "")

                if event_type == "thinking":
                    step_count += 1
                    yield _sse({
                        "type": "thinking",
                        "step": step_count,
                        "agent": event.get("agent", agent_config.id),
                        "content": event.get("thought", "") or event.get("content", ""),
                    })

                elif event_type == "tool_call":
                    tool_name = event.get("tool_name", "")
                    tool_args = event.get("tool_args", {})

                    if tool_name == "delegate":
                        has_delegation = True
                        thought_content = event.get("thought", "") or event.get("content", "")
                        if thought_content:
                            yield _sse({
                                "type": "thinking",
                                "step": step_count,
                                "agent": event.get("agent", agent_config.id),
                                "content": thought_content,
                            })
                        yield _sse({
                            "type": "step",
                            "step": step_count,
                            "agent": event.get("agent", agent_config.id),
                            "tool_name": "delegate",
                            "tool_args": {"role": tool_args.get("role", ""), "task": tool_args.get("task", "")},
                        })
                    else:
                        yield _sse({
                            "type": "step",
                            "step": step_count,
                            "agent": event.get("agent", agent_config.id),
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                        })

                elif event_type == "tool_result":
                    obs = event.get("observation", "")
                    yield _sse({
                        "type": "step",
                        "step": step_count,
                        "agent": event.get("agent", agent_config.id),
                        "observation": obs[:500] if obs else "",
                    })

                elif event_type == "handoff":
                    has_delegation = True
                    step_count += 1
                    yield _sse({
                        "type": "handoff",
                        "from": agent_config.id,
                        "to": event.get("agent", ""),
                        "content": event.get("content", ""),
                        "task": event.get("content", ""),
                    })

                elif event_type == "reflect":
                    step_count += 1
                    yield _sse({
                        "type": "thinking",
                        "step": step_count,
                        "agent": event.get("agent", agent_config.id),
                        "content": f"反思: {event.get('content', '')}",
                    })

                elif event_type == "verify":
                    yield _sse({
                        "type": "step",
                        "step": step_count,
                        "agent": event.get("agent", agent_config.id),
                        "content": event.get("content", ""),
                    })

                elif event_type == "answer":
                    answer = event.get("content", "")
                    if answer:
                        final_answer = answer

                elif event_type == "error":
                    yield _sse({"type": "error", "error": event.get("content", "未知错误")})
        finally:
            if not consumer_task.done():
                consumer_task.cancel()

        if has_delegation:
            task_id = str(uuid.uuid4())
            try:
                await _record_task(task_id, task, agent_config.id, TaskStatus.RUNNING, session_id)
            except Exception:
                pass

        if final_answer:
            yield _sse({"type": "answer_start"})
            chunk_size = 4
            for i in range(0, len(final_answer), chunk_size):
                yield _sse({
                    "type": "token",
                    "content": final_answer[i:i + chunk_size],
                    "finish_reason": "stop" if i + chunk_size >= len(final_answer) else None,
                })
        else:
            yield _sse({"type": "answer_start"})
            yield _sse({"type": "token", "content": "任务执行完成，但未生成有效答案。", "finish_reason": "stop"})

        duration_ms = int((time.time() - start_time) * 1000)
        done_event = {
            "type": "done",
            "stream_id": stream_id,
            "session_id": session_id,
            "steps": step_count,
            "duration_ms": duration_ms,
        }
        if task_id:
            done_event["task_id"] = task_id
        yield _sse(done_event)

        try:
            await _append_session_history(session_id, {"role": "assistant", "content": final_answer, "agent_name": agent_config.name})
        except Exception:
            pass

        if task_id:
            try:
                await _save_result(task_id, {
                    "task_id": task_id,
                    "agent_id": agent_config.id,
                    "agent_name": agent_config.name,
                    "result": final_answer,
                    "steps": step_count,
                })
                await _record_task(task_id, task, agent_config.id, TaskStatus.COMPLETED)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Execute stream failed: {e}")
        yield _sse({"type": "error", "error": str(e)})
        if task_id:
            try:
                await _record_task(task_id, task, agent_config.id, TaskStatus.FAILED)
            except Exception:
                pass

    yield _sse("[DONE]")


@router.post("/stream")
async def chat_stream(req: ChatStreamRequest):
    """统一流式接口

    SSE 事件类型（实时流式 - Supervisor + Worker 模式）：
    - {"type": "start", "stream_id": "...", "session_id": "...", "agent_id": "...", "agent_name": "..."}
    - {"type": "thinking", "step": 1, "agent": "supervisor", "content": "正在分析..."}
    - {"type": "step", "step": 2, "agent": "supervisor", "tool_name": "web_search", "tool_args": {...}}
    - {"type": "step", "step": 2, "agent": "supervisor", "observation": "搜索结果..."}
    - {"type": "handoff", "from": "supervisor", "to": "planner", "task": "规划任务分解"}
    - {"type": "thinking", "step": 3, "agent": "planner", "content": "分解为3个子任务..."}
    - {"type": "answer_start"}
    - {"type": "token", "content": "...", "finish_reason": null|"stop"}
    - {"type": "done", "stream_id": "...", "session_id": "...", "steps": 5, "duration_ms": 12340, "task_id": "仅委派时存在"}
    - {"type": "error", "error": "..."}
    - [DONE]

    任务创建策略：仅当 Supervisor 委派专家智能体（delegate）时创建任务记录，
    简单问答只记录到会话历史，不产生任务。
    """
    agent_config = _get_agent_config(req.agent_id)
    generator = _stream_execute(req.message, agent_config, req.max_steps, req.temperature, req.session_id)

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """获取会话历史"""
    from src.db.repository.session_repo import SessionRepository

    db = await get_db()
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return ApiResponse(success=True, data={
        "session_id": session_id,
        "history": session.get("session_history", []),
    })


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """获取会话列表"""
    from src.db.repository.session_repo import SessionRepository

    db = await get_db()
    repo = SessionRepository(db)
    rows = await repo.fetch_all(
        "SELECT id, status, summary, last_activity_at, created_at FROM sessions ORDER BY last_activity_at DESC LIMIT ?",
        (limit,),
    )

    for row in rows:
        if not row.get("summary"):
            session = await repo.get_by_id(row["id"])
            if session:
                history: list = session.get("session_history", [])
                for msg in history:
                    if msg.get("role") == "user" and msg.get("content"):
                        row["summary"] = msg["content"][:50]
                        try:
                            await repo.update_summary(row["id"], msg["content"][:50])
                        except Exception:
                            pass
                        break

    return ApiResponse(success=True, data={"sessions": rows, "total": len(rows)})


_memory_manager: MemoryManager | None = None
_skill_registry: SkillRegistry | None = None


async def _get_memory_manager() -> MemoryManager | None:
    global _memory_manager
    if _memory_manager is not None:
        return _memory_manager
    try:
        db = await get_db()
        if db is not None:
            repo = MemoryRepository(db)
            _memory_manager = MemoryManager(repo)
            return _memory_manager
    except Exception as e:
        logger.warning(f"Failed to initialize memory manager: {e}")
    return None


async def _get_skill_registry() -> SkillRegistry | None:
    global _skill_registry
    if _skill_registry is not None:
        return _skill_registry
    try:
        from src.skills.registry import get_skill_registry as get_global_registry
        _skill_registry = get_global_registry()
        logger.info(f"Skill registry linked: {_skill_registry.size} skills available")
        return _skill_registry
    except Exception as e:
        logger.warning(f"Failed to link skill registry: {e}")
        return None


async def _record_task(task_id: str, description: str, agent_id: str, status: TaskStatus, session_id: str | None = None) -> None:
    try:
        db = await get_db()
        repo = TaskRepository(db)
        existing = await repo.get_by_id(task_id)
        if existing:
            await repo.update_status(task_id, status)
        else:
            await repo.create(task_id=task_id, description=description, session_id=session_id or str(uuid.uuid4()))
            await repo.assign_agent(task_id, agent_id)
            await repo.update_status(task_id, status)
    except Exception as e:
        logger.warning(f"Failed to record task {task_id}: {e}")


async def _create_session(session_id: str, summary: str | None = None) -> None:
    try:
        db = await get_db()
        from src.db.repository.session_repo import SessionRepository
        repo = SessionRepository(db)
        await repo.create(session_id)
        if summary:
            await repo.update_summary(session_id, summary)
    except Exception as e:
        logger.warning(f"Failed to create session {session_id}: {e}")


async def _append_session_history(session_id: str, message: dict) -> None:
    try:
        db = await get_db()
        from src.db.repository.session_repo import SessionRepository
        repo = SessionRepository(db)
        existing = await repo.get_by_id(session_id)
        if existing is None:
            await repo.create(session_id)
        await repo.append_history(session_id, message)
        if message.get("role") == "user" and existing and not existing.get("summary"):
            content = message.get("content", "")
            if content:
                await repo.update_summary(session_id, content[:50])
    except Exception as e:
        logger.warning(f"Failed to append session history for {session_id}: {e}")


async def _load_session_history(session_id: str) -> list[dict]:
    try:
        db = await get_db()
        from src.db.repository.session_repo import SessionRepository
        repo = SessionRepository(db)
        session = await repo.get_by_id(session_id)
        if session is None:
            return []
        history: list = session.get("session_history", [])
        if not history:
            return []
        history = history[:-1] if len(history) > 1 else []
        max_turns = 10
        if len(history) > max_turns * 2:
            history = history[-(max_turns * 2):]
        return history
    except Exception as e:
        logger.warning(f"Failed to load session history for {session_id}: {e}")
        return []


async def _save_result(task_id: str, result: dict) -> None:
    try:
        db = await get_db()
        repo = TaskRepository(db)
        await repo.update_result(task_id, result)
    except Exception as e:
        logger.warning(f"Failed to save result for {task_id}: {e}")