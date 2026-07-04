from __future__ import annotations

from enum import Enum

from src.common.logger import logger
from src.core.reasoning import ReasoningEngine
from src.tools.tool_dispatcher import ToolDispatcher


class DecisionType(str, Enum):
    THINK = "think"
    ACTION_TOOL = "action_tool"
    ACTION_LLM = "action_llm"
    FINAL_ANSWER = "final_answer"
    REFLECT = "reflect"


class DecisionDispatcher:
    def __init__(
        self,
        reasoning: ReasoningEngine,
        tool_dispatcher: ToolDispatcher,
        error_threshold: int = 3,
    ):
        self._reasoning = reasoning
        self._tool_dispatcher = tool_dispatcher
        self._error_threshold = error_threshold
        self._error_count = 0

    def route(self, current_state: dict) -> DecisionType:
        if current_state.get("has_tool_call"):
            return DecisionType.ACTION_TOOL
        if current_state.get("needs_more_reasoning"):
            return DecisionType.THINK
        if current_state.get("needs_reflection"):
            return DecisionType.REFLECT
        return DecisionType.FINAL_ANSWER

    def prioritize(self, pending_actions: list[dict]) -> list[dict]:
        return sorted(pending_actions, key=lambda x: x.get("priority", 5))

    def circuit_breaker(self, error_count: int | None = None) -> bool:
        count = error_count if error_count is not None else self._error_count
        if count >= self._error_threshold:
            logger.warning("熔断器触发: 错误次数 %d 达到阈值 %d", count, self._error_threshold)
            return True
        return False

    def record_error(self) -> None:
        self._error_count += 1

    def reset_errors(self) -> None:
        self._error_count = 0

    async def execute_decision(
        self, decision: DecisionType, context: dict, plan_id: str | None = None
    ) -> dict:
        if decision == DecisionType.THINK:
            thought = await self._reasoning.think(context, plan_id)
            return {"decision": "think", "thought": thought}

        if decision == DecisionType.ACTION_TOOL:
            thought = context.get("last_thought", context.get("user_input", ""))
            action = await self._reasoning.decide_action(thought, context)
            tool_name = action.get("name", action.get("tool_name", ""))
            tool_params = action.get("parameters", action.get("params", {}))
            if tool_name:
                result = await self._tool_dispatcher.dispatch_with_retry(
                    tool_name=tool_name, params=tool_params,
                )
                self.reset_errors()
                return {
                    "decision": "action_tool",
                    "tool_name": tool_name,
                    "result": result.model_dump(),
                }
            return {"decision": "action_tool", "result": action}

        if decision == DecisionType.REFLECT:
            reflect_context = dict(context)
            reflect_context["user_input"] = (
                f"请反思之前的执行过程，判断是否偏离目标：\n"
                f"目标: {context.get('goal', '')}\n"
                f"当前状态: {context.get('last_thought', '')}"
            )
            reflection = await self._reasoning.think(reflect_context, plan_id)
            return {"decision": "reflect", "reflection": reflection}

        return {"decision": "final_answer", "content": context.get("last_thought", "")}