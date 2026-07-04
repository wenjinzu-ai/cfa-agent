from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.reasoning import ReasoningEngine, ReasoningStrategy
from src.llm.base import BaseLLM
from src.models.message import ChatMessage, Role, StreamEvent, EventType
from src.tools.registry import ToolRegistry


class _MockLLM(BaseLLM):
    def __init__(self, responses=None):
        self.responses = responses or ["Thought: 分析问题\nFinal Answer: 完成"]
        self._call_count = 0

    async def chat(self, messages, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        resp = self.responses[idx]
        self._call_count += 1
        return resp

    async def chat_stream(self, messages, **kwargs):
        yield StreamEvent(event_type=EventType.THOUGHT, content="思考中...")

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
def llm():
    return _MockLLM()


@pytest.fixture
def engine(llm, registry):
    return ReasoningEngine(llm=llm, registry=registry)


class TestReasoningEngine:
    @pytest.mark.asyncio
    async def test_think_basic(self, engine):
        context = {
            "user_input": "什么是 Python?",
            "history": [],
            "relevant_memory": [],
        }
        result = await engine.think(context)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_think_with_plan_id(self, engine):
        context = {
            "user_input": "测试",
            "history": [],
            "relevant_memory": [],
        }
        result = await engine.think(context, plan_id="plan-123")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_think_stream(self, engine):
        context = {
            "user_input": "测试流式",
            "history": [],
            "relevant_memory": [],
        }
        events = []
        async for event in engine.think_stream(context, plan_id="plan-456"):
            events.append(event)

        assert len(events) >= 1
        assert events[0].event_type == EventType.THOUGHT
        assert events[0].plan_id == "plan-456"

    @pytest.mark.asyncio
    async def test_decide_action_json(self, engine):
        json_llm = _MockLLM(responses=['{"name": "web_search", "parameters": {"query": "test"}}'])
        engine._llm = json_llm

        context = {"history": []}
        result = await engine.decide_action("搜索测试", context)
        assert result.get("name") == "web_search"

    @pytest.mark.asyncio
    async def test_decide_action_plain_text(self, engine):
        text_llm = _MockLLM(responses=["这是纯文本回复，不是JSON"])
        engine._llm = text_llm

        context = {"history": []}
        result = await engine.decide_action("普通问题", context)
        assert result.get("action_type") == "final_answer"
        assert result.get("content") == "这是纯文本回复，不是JSON"

    @pytest.mark.asyncio
    async def test_think_with_memory(self, engine):
        context = {
            "user_input": "继续讨论",
            "history": [],
            "relevant_memory": ["之前讨论了 Python 异步编程"],
        }
        result = await engine.think(context)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_think_llm_error(self, engine):
        failing_llm = AsyncMock(spec=BaseLLM)
        failing_llm.chat = AsyncMock(side_effect=Exception("LLM 服务不可用"))
        engine._llm = failing_llm

        from src.common.exceptions import LLMError
        with pytest.raises(LLMError):
            await engine.think({"user_input": "测试", "history": [], "relevant_memory": []})


class TestReasoningStrategy:
    def test_select_strategy_react_when_needs_tool(self, engine):
        context = {"needs_tool": True, "needs_multi_step": False}
        strategy = engine.select_strategy(context)
        assert strategy == ReasoningStrategy.REACT

    def test_select_strategy_single_cot_when_simple(self, engine):
        context = {"needs_tool": False, "needs_multi_step": False}
        strategy = engine.select_strategy(context)
        assert strategy == ReasoningStrategy.SINGLE_COT

    def test_select_strategy_tot_when_multiple_paths(self, engine):
        context = {"needs_tool": False, "needs_multi_step": True, "has_multiple_paths": True}
        strategy = engine.select_strategy(context)
        assert strategy == ReasoningStrategy.TOT

    def test_select_strategy_multi_cot_when_multi_step(self, engine):
        context = {"needs_tool": False, "needs_multi_step": True, "has_multiple_paths": False}
        strategy = engine.select_strategy(context)
        assert strategy == ReasoningStrategy.MULTI_COT

    def test_select_strategy_tool_takes_priority(self, engine):
        context = {"needs_tool": True, "needs_multi_step": True, "has_multiple_paths": True}
        strategy = engine.select_strategy(context)
        assert strategy == ReasoningStrategy.REACT

    @pytest.mark.asyncio
    async def test_think_with_strategy_single_cot(self, engine):
        context = {
            "user_input": "简单问题",
            "history": [],
            "relevant_memory": [],
            "needs_tool": False,
            "needs_multi_step": False,
        }
        result = await engine.think_with_strategy(context)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_think_with_strategy_react(self, engine):
        context = {
            "user_input": "搜索天气",
            "history": [],
            "relevant_memory": [],
            "needs_tool": True,
        }
        result = await engine.think_with_strategy(context)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_think_with_strategy_with_plan_id(self, engine):
        context = {
            "user_input": "测试",
            "history": [],
            "relevant_memory": [],
            "needs_tool": False,
            "needs_multi_step": False,
        }
        result = await engine.think_with_strategy(context, plan_id="plan-789")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_think_with_strategy_llm_error(self, engine):
        failing_llm = AsyncMock(spec=BaseLLM)
        failing_llm.chat = AsyncMock(side_effect=Exception("LLM 不可用"))
        engine._llm = failing_llm

        from src.common.exceptions import LLMError
        with pytest.raises(LLMError):
            await engine.think_with_strategy({
                "user_input": "测试",
                "history": [],
                "relevant_memory": [],
                "needs_tool": False,
            })


class TestReasoningStrategyEnum:
    def test_strategy_values(self):
        assert ReasoningStrategy.SINGLE_COT.value == "single_cot"
        assert ReasoningStrategy.MULTI_COT.value == "multi_cot"
        assert ReasoningStrategy.REACT.value == "react"
        assert ReasoningStrategy.TOT.value == "tot"

    def test_strategy_is_string_enum(self):
        assert isinstance(ReasoningStrategy.REACT, str)
        assert ReasoningStrategy.REACT == "react"