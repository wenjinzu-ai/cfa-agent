from pydantic import BaseModel, Field
from enum import Enum
from typing import Any
from datetime import datetime, timezone
import uuid


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: Role
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventType(str, Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    RESULT = "result"
    PLAN_UPDATE = "plan_update"
    ERROR = "error"
    ANSWER = "answer"


class EventCategory(str, Enum):
    DECISION = "decision"
    TOOL_CALL = "tool_call"
    GUARDRAIL = "guardrail"


class StreamEvent(BaseModel):
    event_type: EventType
    event_category: EventCategory | None = None
    plan_id: str | None = None
    step_id: int | None = None
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="会话ID，为空则自动生成")
    stream: bool = Field(default=False, description="是否流式输出")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    plan_id: str | None = None
    steps_executed: int = 0
    token_usage: dict[str, int] = Field(default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0})