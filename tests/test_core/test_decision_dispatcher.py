from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.decision_dispatcher import DecisionDispatcher, DecisionType
from src.core.reasoning import ReasoningEngine
from src.llm.base import BaseLLM
from src.tools.registry import ToolRegistry
from src.tools.tool_dispatcher import ToolDispatcher


class _MockLLM(BaseLLM):
    def __init__(self, responses=None):
        self.responses = responses or ["Thought: 分析\nFinal Answer: 完成"]
        self._call_count = 0

    async def chat(self, messages, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        resp = self.responses[idx]
        self._call_count += 1
        return resp

    async def chat_stream(self, messages, **kwargs):
        from src.models.message import StreamEvent, EventType
        yield StreamEvent(event_type=EventType.THOUGHT, content="思考中")

    async def chat_with_tools(self, messages, tools, **kwargs):
        return {"content": self.responses[0], "tool_calls": []}

    def count_tokens(self, messages):
        return 10

    async def close(self):
        pass


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.clear()
    return r


@pytest.fixture
def reasoning(registry):
    llm = _MockLLM()
    return ReasoningEngine(llm=llm, registry=registry)


@pytest.fixture
def tool_dispatcher(registry):
    return ToolDispatcher(registry=registry)


@pytest.fixture
def dispatcher(reasoning, tool_dispatcher):
    return DecisionDispatcher(reasoning=reasoning, tool_dispatcher=tool_dispatcher)


class TestDecisionType:
    def test_decision_types_exist(self):
        assert DecisionType.THINK == "think"
        assert DecisionType.ACTION_TOOL == "action_tool"
        assert DecisionType.ACTION_LLM == "action_llm"
        assert DecisionType.FINAL_ANSWER == "final_answer"
        assert DecisionType.REFLECT == "reflect"


class TestDecisionDispatcherRouting:
    def test_route_tool_call(self, dispatcher):
        state = {"has_tool_call": True}
        assert dispatcher.route(state) == DecisionType.ACTION_TOOL

    def test_route_think(self, dispatcher):
        state = {"needs_more_reasoning": True}
        assert dispatcher.route(state) == DecisionType.THINK

    def test_route_reflect(self, dispatcher):
        state = {"needs_reflection": True}
        assert dispatcher.route(state) == DecisionType.REFLECT

    def test_route_final_answer(self, dispatcher):
        state = {}
        assert dispatcher.route(state) == DecisionType.FINAL_ANSWER

    def test_route_tool_call_priority(self, dispatcher):
        state = {"has_tool_call": True, "needs_more_reasoning": True}
        assert dispatcher.route(state) == DecisionType.ACTION_TOOL


class TestDecisionDispatcherPrioritize:
    def test_prioritize_by_priority(self, dispatcher):
        actions = [
            {"name": "low", "priority": 8},
            {"name": "high", "priority": 1},
            {"name": "mid", "priority": 5},
        ]
        result = dispatcher.prioritize(actions)
        assert result[0]["name"] == "high"
        assert result[1]["name"] == "mid"
        assert result[2]["name"] == "low"

    def test_prioritize_default_priority(self, dispatcher):
        actions = [
            {"name": "a"},
            {"name": "b", "priority": 1},
        ]
        result = dispatcher.prioritize(actions)
        assert result[0]["name"] == "b"

    def test_prioritize_empty(self, dispatcher):
        assert dispatcher.prioritize([]) == []


class TestDecisionDispatcherCircuitBreaker:
    def test_circuit_breaker_not_triggered(self, dispatcher):
        assert not dispatcher.circuit_breaker(error_count=0)
        assert not dispatcher.circuit_breaker(error_count=2)

    def test_circuit_breaker_triggered(self, dispatcher):
        assert dispatcher.circuit_breaker(error_count=3)

    def test_circuit_breaker_default_threshold(self, dispatcher):
        dispatcher._error_count = 3
        assert dispatcher.circuit_breaker()

    def test_circuit_breaker_custom_threshold(self):
        from src.core.reasoning import ReasoningEngine
        from src.tools.tool_dispatcher import ToolDispatcher
        from src.tools.registry import ToolRegistry
        r = ToolRegistry()
        r.clear()
        reasoning = ReasoningEngine(llm=_MockLLM(), registry=r)
        td = ToolDispatcher(registry=r)
        d = DecisionDispatcher(reasoning=reasoning, tool_dispatcher=td, error_threshold=5)
        assert not d.circuit_breaker(error_count=4)
        assert d.circuit_breaker(error_count=5)

    def test_record_and_reset_errors(self, dispatcher):
        dispatcher.record_error()
        dispatcher.record_error()
        assert dispatcher._error_count == 2
        dispatcher.reset_errors()
        assert dispatcher._error_count == 0


class TestDecisionDispatcherExecute:
    @pytest.mark.asyncio
    async def test_execute_think(self, dispatcher):
        context = {"user_input": "测试", "history": [], "relevant_memory": []}
        result = await dispatcher.execute_decision(DecisionType.THINK, context)
        assert result["decision"] == "think"
        assert "thought" in result

    @pytest.mark.asyncio
    async def test_execute_final_answer(self, dispatcher):
        context = {"last_thought": "最终答案"}
        result = await dispatcher.execute_decision(DecisionType.FINAL_ANSWER, context)
        assert result["decision"] == "final_answer"
        assert result["content"] == "最终答案"

    @pytest.mark.asyncio
    async def test_execute_reflect(self, dispatcher):
        context = {"goal": "完成任务", "last_thought": "当前进度", "history": []}
        result = await dispatcher.execute_decision(DecisionType.REFLECT, context)
        assert result["decision"] == "reflect"
        assert "reflection" in result