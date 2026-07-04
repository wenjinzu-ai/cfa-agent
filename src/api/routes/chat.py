from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from src.api.deps import get_agent
from src.common.exceptions import InputGuardrailError
from src.common.logger import logger
from src.models.message import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    agent = get_agent()
    try:
        response = await agent.run(request)
        return response
    except InputGuardrailError:
        raise HTTPException(status_code=400, detail="输入被安全护栏拦截")
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    agent = get_agent()

    async def event_generator():
        try:
            async for event in agent.run_stream(request):
                yield {
                    "event": event.event_type.value,
                    "data": json.dumps(
                        {
                            "event_type": event.event_type.value,
                            "event_category": event.event_category.value if event.event_category else None,
                            "plan_id": event.plan_id,
                            "step_id": event.step_id,
                            "content": event.content,
                            "timestamp": event.timestamp,
                        },
                        ensure_ascii=False,
                    ),
                }
        except Exception as e:
            logger.error("Stream error: %s", e)
            yield {
                "event": "error",
                "data": json.dumps({"content": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())