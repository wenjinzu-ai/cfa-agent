from __future__ import annotations

import json
import uuid

from src.common.logger import logger
from src.guardrails.guardrail_manager import GuardrailManager
from src.llm.base import BaseLLM
from src.llm.prompt_manager import PromptManager
from src.memory.retrieval import MemoryRetriever
from src.memory.sqlite_store import SQLiteStore
from src.models.message import ChatMessage, ChatRequest, Role


class IntentType:
    SIMPLE_CHAT = "simple_chat"
    SIMPLE_QA = "simple_qa"
    COMPLEX_TASK = "complex_task"

    @classmethod
    def valid_values(cls) -> set[str]:
        return {cls.SIMPLE_CHAT, cls.SIMPLE_QA, cls.COMPLEX_TASK}


class PerceptionEngine:
    def __init__(self, store: SQLiteStore, guardrail_manager: GuardrailManager, llm: BaseLLM):
        self._store = store
        self._guardrail_manager = guardrail_manager
        self._retriever = MemoryRetriever(store)
        self._llm = llm

    async def classify_intent(self, message: str) -> str:
        prompt_mgr = PromptManager.get_instance()
        system_prompt, user_prompt = prompt_mgr.get(
            "intent/classify",
            user_input=message,
        )

        messages = [
            ChatMessage(role=Role.SYSTEM, content=system_prompt),
            ChatMessage(role=Role.USER, content=user_prompt),
        ]

        try:
            raw = await self._llm.chat(messages)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned)
            intent = parsed.get("intent", "")

            if intent in IntentType.valid_values():
                logger.info("意图识别(LLM): [%s] -> %s", message[:30], intent)
                return intent

            logger.warning("意图识别(LLM)返回未知类型: %s, 降级为 simple_qa", intent)
        except json.JSONDecodeError:
            logger.warning("意图识别(LLM)JSON解析失败: %s, 降级为 simple_qa", raw[:100])
        except Exception as e:
            logger.warning("意图识别(LLM)异常: %s, 降级为 simple_qa", e)

        return IntentType.SIMPLE_QA

    async def perceive(self, request: ChatRequest) -> dict:
        guardrail_result = await self._guardrail_manager.check_input(request.message)
        user_content = guardrail_result.sanitized_content or request.message

        relevant_memory: list[str] = []
        try:
            results = await self._retriever.combined_search(request.message, limit=5)
            relevant_memory = [r.entry.content for r in results if r.score > 0.3]
        except Exception as e:
            logger.warning("记忆检索失败: %s", e)

        session_id = request.session_id or self._generate_session_id()
        history: list[ChatMessage] = []
        if request.session_id:
            rows = await self._store.get_conversation_history(request.session_id, limit=20)
            for row in rows:
                history.append(ChatMessage(role=Role(row["role"]), content=row["content"]))

        intent = await self.classify_intent(user_content)

        return {
            "user_input": user_content,
            "original_input": request.message,
            "history": [m.model_dump() for m in history],
            "relevant_memory": relevant_memory,
            "session_id": session_id,
            "intent": intent,
        }

    @staticmethod
    def _generate_session_id() -> str:
        return str(uuid.uuid4())