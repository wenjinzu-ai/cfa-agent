from __future__ import annotations

import json
from enum import Enum
from typing import AsyncIterator

from src.common.exceptions import LLMError
from src.common.logger import logger
from src.llm.base import BaseLLM
from src.llm.prompt_manager import PromptManager
from src.models.message import StreamEvent
from src.tools.registry import ToolRegistry


class ReasoningStrategy(str, Enum):
    SINGLE_COT = "single_cot"
    MULTI_COT = "multi_cot"
    REACT = "react"
    TOT = "tot"


class ReasoningEngine:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry | None = None):
        self._llm = llm
        self._registry = registry or ToolRegistry.get_instance()

    async def think_simple(self, context: dict) -> str:
        intent = context.get("intent", "simple_qa")
        template_key = "reasoning/simple_chat" if intent == "simple_chat" else "reasoning/cot"
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            template_key,
            history=context.get("history", []),
            question=context.get("user_input", ""),
        )
        try:
            response = await self._llm.chat(
                [self._dict_to_chat_message(m) for m in messages],
            )
            return response
        except Exception as e:
            logger.error("推理引擎 think_simple 失败: %s", e)
            raise LLMError(message=str(e)) from e

    async def think_simple_stream(self, context: dict) -> AsyncIterator[StreamEvent]:
        intent = context.get("intent", "simple_qa")
        template_key = "reasoning/simple_chat" if intent == "simple_chat" else "reasoning/cot"
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            template_key,
            history=context.get("history", []),
            question=context.get("user_input", ""),
        )
        try:
            from src.models.message import EventType
            async for event in self._llm.chat_stream(
                [self._dict_to_chat_message(m) for m in messages],
            ):
                yield StreamEvent(
                    event_type=EventType.ANSWER,
                    content=event.content,
                )
        except Exception as e:
            logger.error("推理引擎 think_simple_stream 失败: %s", e)
            raise LLMError(message=str(e)) from e

    async def summarize_stream(self, summary_input: str) -> AsyncIterator[StreamEvent]:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/simple_chat",
            question=summary_input,
        )
        try:
            from src.models.message import EventType
            async for event in self._llm.chat_stream(
                [self._dict_to_chat_message(m) for m in messages],
            ):
                yield StreamEvent(
                    event_type=EventType.ANSWER,
                    content=event.content,
                )
        except Exception as e:
            logger.error("推理引擎 summarize_stream 失败: %s", e)
            raise LLMError(message=str(e)) from e

    async def think(self, context: dict, plan_id: str | None = None) -> str:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/react",
            history=context.get("history", []),
            question=context.get("user_input", ""),
            tools_description=self._format_tools(),
            relevant_memory="\n".join(context.get("relevant_memory", [])),
        )
        try:
            response = await self._llm.chat(
                [self._dict_to_chat_message(m) for m in messages],
            )
            return response
        except Exception as e:
            logger.error("推理引擎 think 失败: %s", e)
            raise LLMError(message=str(e), detail={"plan_id": plan_id}) from e

    async def think_stream(
        self, context: dict, plan_id: str | None = None
    ) -> AsyncIterator[StreamEvent]:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/react",
            history=context.get("history", []),
            question=context.get("user_input", ""),
            tools_description=self._format_tools(),
            relevant_memory="\n".join(context.get("relevant_memory", [])),
        )
        async for event in self._llm.chat_stream(
            [self._dict_to_chat_message(m) for m in messages],
        ):
            event.plan_id = plan_id
            yield event

    async def decide_action(self, thought: str, context: dict) -> dict:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "tools/tool_call",
            history=context.get("history", []),
            step_description=thought,
            tools_schema=json.dumps(
                self._registry.list_schemas_for_llm(), ensure_ascii=False
            ),
        )
        result = await self._llm.chat(
            [self._dict_to_chat_message(m) for m in messages],
        )
        try:
            action = json.loads(result)
            return action
        except json.JSONDecodeError:
            return {"action_type": "final_answer", "content": result}

    def select_strategy(self, context: dict) -> ReasoningStrategy:
        needs_tool = context.get("needs_tool", False)
        needs_multi_step = context.get("needs_multi_step", False)
        has_multiple_paths = context.get("has_multiple_paths", False)

        if needs_tool:
            return ReasoningStrategy.REACT
        if not needs_multi_step:
            return ReasoningStrategy.SINGLE_COT
        if has_multiple_paths:
            return ReasoningStrategy.TOT
        return ReasoningStrategy.MULTI_COT

    async def think_with_strategy(
        self, context: dict, plan_id: str | None = None
    ) -> str:
        strategy = self.select_strategy(context)
        template_key = {
            ReasoningStrategy.SINGLE_COT: "reasoning/cot",
            ReasoningStrategy.MULTI_COT: "reasoning/cot",
            ReasoningStrategy.REACT: "reasoning/react",
            ReasoningStrategy.TOT: "reasoning/cot",
        }[strategy]

        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            template_key,
            history=context.get("history", []),
            question=context.get("user_input", ""),
            tools_description=self._format_tools() if strategy == ReasoningStrategy.REACT else "",
            relevant_memory="\n".join(context.get("relevant_memory", [])),
        )
        try:
            response = await self._llm.chat(
                [self._dict_to_chat_message(m) for m in messages],
            )
            return response
        except Exception as e:
            logger.error("推理引擎 think_with_strategy 失败: %s", e)
            raise LLMError(message=str(e), detail={"plan_id": plan_id, "strategy": strategy.value}) from e

    def _format_tools(self) -> str:
        lines = []
        for t in self._registry.list_tools():
            params = t.parameters.get("properties", {})
            param_desc = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in params.items())
            lines.append(f"- {t.name}({param_desc}): {t.description}")
        return "\n".join(lines) if lines else "无可用工具"

    @staticmethod
    def _dict_to_chat_message(msg: dict):
        from src.models.message import ChatMessage, Role
        return ChatMessage(
            role=Role(msg.get("role", "user")),
            content=msg.get("content", ""),
        )