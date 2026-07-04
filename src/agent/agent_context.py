from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.guardrails.guardrail_manager import GuardrailManager
from src.llm.base import BaseLLM
from src.memory.working_memory import WorkingMemory
from src.models.message import ChatMessage
from src.tools.tool_dispatcher import ToolDispatcher


@dataclass
class AgentContext:
    session_id: str
    llm: BaseLLM
    working_memory: WorkingMemory
    tool_dispatcher: ToolDispatcher
    guardrail_manager: GuardrailManager
    conversation_history: list[ChatMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **meta) -> None:
        from src.models.message import Role
        self.conversation_history.append(
            ChatMessage(role=Role(role), content=content, metadata=meta)
        )

    def get_messages(self) -> list[ChatMessage]:
        return list(self.conversation_history)

    def clear_history(self) -> None:
        self.conversation_history.clear()