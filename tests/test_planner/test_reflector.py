from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm.base import BaseLLM
from src.memory.sqlite_store import SQLiteStore
from src.models.message import ChatMessage, Role
from src.planner.reflector import Reflector


class _MockLLM(BaseLLM):
    def __init__(self, responses=None):
        self.responses = responses or ["评估结论：满意\n分析：结果符合预期\n改进建议：无"]
        self._call_count = 0

    async def chat(self, messages, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        resp = self.responses[idx]
        self._call_count += 1
        return resp

    async def chat_stream(self, messages, **kwargs):
        from src.models.message import StreamEvent, EventType
        yield StreamEvent(event_type=EventType.THOUGHT, content="反思中")

    async def chat_with_tools(self, messages, tools, **kwargs):
        return {"content": self.responses[0], "tool_calls": []}

    def count_tokens(self, messages):
        return 10

    async def close(self):
        pass


@pytest.fixture
async def store(tmp_path):
    db = SQLiteStore(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def llm():
    return _MockLLM()


@pytest.fixture
def reflector(store, llm):
    return Reflector(store=store, llm=llm)


class TestReflectorEvaluateResult:
    @pytest.mark.asyncio
    async def test_evaluate_satisfactory_result(self, reflector):
        result = await reflector.evaluate_result(
            step_description="搜索 Python 教程",
            result="找到了 3 篇优质教程",
            goal="学习 Python",
        )
        assert "is_satisfactory" in result
        assert "analysis" in result
        assert isinstance(result["is_satisfactory"], bool)

    @pytest.mark.asyncio
    async def test_evaluate_unsatisfactory_result(self, reflector):
        unsatisfied_llm = _MockLLM(responses=["评估结论：不满意\n分析：失败，未获取有效结果\n改进建议：更换搜索关键词"])
        reflector._llm = unsatisfied_llm
        result = await reflector.evaluate_result(
            step_description="搜索资料",
            result="",
            goal="获取资料",
        )
        assert result["is_satisfactory"] is False
        assert "不满意" in result["analysis"] or "失败" in result["analysis"]

    @pytest.mark.asyncio
    async def test_evaluate_handles_llm_error(self, reflector):
        failing_llm = AsyncMock(spec=BaseLLM)
        failing_llm.chat = AsyncMock(side_effect=Exception("LLM 不可用"))
        reflector._llm = failing_llm

        result = await reflector.evaluate_result(
            step_description="测试步骤",
            result="结果",
            goal="目标",
        )
        assert result["is_satisfactory"] is True
        assert "评估失败" in result["analysis"]


class TestReflectorAnalyzeStrategy:
    @pytest.mark.asyncio
    async def test_analyze_strategy_basic(self, reflector):
        result = await reflector.analyze_strategy(
            plan_goal="完成项目报告",
            completed_steps=[{"description": "收集数据", "result": "完成"}],
            failed_steps=[],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_analyze_strategy_with_failures(self, reflector):
        result = await reflector.analyze_strategy(
            plan_goal="完成任务",
            completed_steps=[{"description": "步骤1", "result": "ok"}],
            failed_steps=[
                {"description": "步骤2", "result": "超时"},
                {"description": "步骤3", "result": "权限不足"},
            ],
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_analyze_strategy_handles_llm_error(self, reflector):
        failing_llm = AsyncMock(spec=BaseLLM)
        failing_llm.chat = AsyncMock(side_effect=Exception("LLM 不可用"))
        reflector._llm = failing_llm

        result = await reflector.analyze_strategy(
            plan_goal="目标", completed_steps=[], failed_steps=[]
        )
        assert "策略分析失败" in result


class TestReflectorSaveExperience:
    @pytest.mark.asyncio
    async def test_save_experience_basic(self, reflector):
        entry_id = await reflector.save_experience(
            task_description="搜索 Python 教程",
            outcome="成功找到 3 篇教程",
        )
        assert isinstance(entry_id, int)
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_save_experience_with_tags(self, reflector):
        entry_id = await reflector.save_experience(
            task_description="代码审查",
            outcome="发现 2 个 bug",
            tags=["code_review", "bug"],
        )
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_save_experience_persisted(self, reflector, store):
        entry_id = await reflector.save_experience(
            task_description="测试任务",
            outcome="测试结果",
        )
        row = await store.find_one("memory_entries", conditions={"id": entry_id})
        assert row is not None
        assert "测试任务" in row["content"]