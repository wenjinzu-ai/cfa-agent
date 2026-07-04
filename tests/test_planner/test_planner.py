from __future__ import annotations

import pytest

from src.llm.base import BaseLLM
from src.memory.sqlite_store import SQLiteStore
from src.models.message import ChatMessage, Role
from src.models.plan import ActionType, Plan, PlanStatus, Step, StepStatus
from src.planner.planner import Planner


class _MockLLM(BaseLLM):
    def __init__(self, responses=None):
        self.responses = responses or [
            "1. 分析问题\n2. 搜索信息\n3. 总结答案"
        ]
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
async def store(tmp_path):
    db = SQLiteStore(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def llm():
    return _MockLLM()


@pytest.fixture
def planner(store, llm):
    return Planner(store=store, llm=llm)


class TestPlannerCreatePlan:
    @pytest.mark.asyncio
    async def test_create_plan_basic(self, planner):
        plan = await planner.create_plan("搜索 Python 资料", session_id="s1")
        assert isinstance(plan, Plan)
        assert plan.session_id == "s1"
        assert plan.goal == "搜索 Python 资料"
        assert plan.status == PlanStatus.RUNNING
        assert len(plan.steps) >= 1

    @pytest.mark.asyncio
    async def test_create_plan_parses_steps(self, planner):
        plan = await planner.create_plan("完成任务", session_id="s2")
        assert len(plan.steps) == 3
        assert plan.steps[0].step_id == 1
        assert plan.steps[0].description == "分析问题"
        assert plan.steps[1].description == "搜索信息"
        assert plan.steps[2].description == "总结答案"

    @pytest.mark.asyncio
    async def test_create_plan_persisted(self, planner, store):
        plan = await planner.create_plan("持久化测试", session_id="s3")
        row = await store.find_one("plans", conditions={"id": plan.plan_id})
        assert row is not None
        assert row["goal"] == "持久化测试"

    @pytest.mark.asyncio
    async def test_create_plan_fallback_on_llm_error(self, store):
        failing_llm = _MockLLM()
        failing_llm.chat = lambda *a, **kw: (_ for _ in ()).throw(Exception("LLM 不可用"))

        class _SyncLLM(BaseLLM):
            async def chat(self, messages, **kwargs):
                raise Exception("LLM 不可用")
            async def chat_stream(self, messages, **kwargs):
                pass
            async def chat_with_tools(self, messages, tools, **kwargs):
                return {"content": "", "tool_calls": []}
            def count_tokens(self, messages):
                return 0
            async def close(self):
                pass

        p = Planner(store=store, llm=_SyncLLM())
        plan = await p.create_plan("回退测试", session_id="s4")
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "回退测试"


class TestPlannerUpdateStep:
    @pytest.mark.asyncio
    async def test_update_step_status(self, planner):
        plan = await planner.create_plan("测试步骤更新", session_id="s5")
        step = plan.steps[0]

        updated = await planner.update_step(plan, step.step_id, StepStatus.RUNNING)
        assert updated.steps[0].status == StepStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_step_with_result(self, planner):
        plan = await planner.create_plan("测试结果", session_id="s6")
        step = plan.steps[0]

        updated = await planner.update_step(
            plan, step.step_id, StepStatus.DONE, result="执行完成"
        )
        assert updated.steps[0].status == StepStatus.DONE
        assert updated.steps[0].result == "执行完成"


class TestPlannerCompleteAndFail:
    @pytest.mark.asyncio
    async def test_complete_plan(self, planner):
        plan = await planner.create_plan("完成测试", session_id="s7")
        completed = await planner.complete_plan(plan)
        assert completed.status == PlanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_fail_plan(self, planner):
        plan = await planner.create_plan("失败测试", session_id="s8")
        failed = await planner.fail_plan(plan, reason="执行出错")
        assert failed.status == PlanStatus.FAILED


class TestPlannerGetNextStep:
    @pytest.mark.asyncio
    async def test_get_next_step_pending(self, planner):
        plan = await planner.create_plan("下一步测试", session_id="s9")
        next_step = await planner.get_next_step(plan)
        assert next_step is not None
        assert next_step.status == StepStatus.PENDING
        assert next_step.step_id == 1

    @pytest.mark.asyncio
    async def test_get_next_step_none(self, planner):
        plan = await planner.create_plan("全部完成", session_id="s10")
        for step in plan.steps:
            step.status = StepStatus.DONE
        next_step = await planner.get_next_step(plan)
        assert next_step is None


class TestPlannerGetPlan:
    @pytest.mark.asyncio
    async def test_get_plan_existing(self, planner):
        plan = await planner.create_plan("获取测试", session_id="s11")
        retrieved = await planner.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.plan_id == plan.plan_id
        assert retrieved.goal == "获取测试"

    @pytest.mark.asyncio
    async def test_get_plan_nonexistent(self, planner):
        result = await planner.get_plan("nonexistent-id")
        assert result is None


class TestPlannerParseSteps:
    @pytest.mark.asyncio
    async def test_parse_numbered_list(self, planner):
        steps = planner._parse_steps("1. 第一步\n2. 第二步\n3. 第三步")
        assert len(steps) == 3
        assert steps[0].description == "第一步"

    @pytest.mark.asyncio
    async def test_parse_dash_list(self, planner):
        steps = planner._parse_steps("- 项目A\n- 项目B")
        assert len(steps) == 2

    @pytest.mark.asyncio
    async def test_parse_empty_fallback(self, planner):
        steps = planner._parse_steps("")
        assert len(steps) == 1
        assert steps[0].description == "执行任务"


class TestPlannerRollbackStep:
    @pytest.mark.asyncio
    async def test_rollback_step_resets_to_pending(self, planner):
        plan = await planner.create_plan("回滚测试", session_id="rb1")
        step = plan.steps[0]
        plan = await planner.update_step(plan, step.step_id, StepStatus.RUNNING, result="执行中")

        rolled = await planner.rollback_step(plan, step.step_id)
        assert rolled.steps[0].status == StepStatus.PENDING
        assert rolled.steps[0].result is None
        assert rolled.steps[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_rollback_step_updates_rollback_point(self, planner):
        plan = await planner.create_plan("快照测试", session_id="rb2")
        step = plan.steps[0]
        plan = await planner.update_step(plan, step.step_id, StepStatus.DONE, result="完成")

        rolled = await planner.rollback_step(plan, step.step_id)
        assert rolled.rollback_point.step_id == 0

    @pytest.mark.asyncio
    async def test_rollback_step_increments_retry_count(self, planner):
        plan = await planner.create_plan("重试测试", session_id="rb3")
        step = plan.steps[0]

        rolled = await planner.rollback_step(plan, step.step_id)
        assert rolled.steps[0].retry_count == 1

        rolled = await planner.rollback_step(rolled, step.step_id)
        assert rolled.steps[0].retry_count == 2


class TestPlannerRollbackPlan:
    @pytest.mark.asyncio
    async def test_rollback_plan_resets_subsequent_steps(self, planner):
        plan = await planner.create_plan("Plan回滚测试", session_id="rb4")
        for step in plan.steps:
            plan = await planner.update_step(plan, step.step_id, StepStatus.DONE, result="完成")

        plan.rollback_point.step_id = 0
        rolled = await planner.rollback_plan(plan)
        for step in rolled.steps:
            if step.step_id > 0:
                assert step.status == StepStatus.PENDING
                assert step.result is None
                assert step.retry_count == 0

    @pytest.mark.asyncio
    async def test_rollback_plan_preserves_earlier_steps(self, planner):
        plan = await planner.create_plan("部分回滚", session_id="rb5")
        if len(plan.steps) >= 2:
            plan = await planner.update_step(plan, 1, StepStatus.DONE, result="步骤1完成")
            plan.rollback_point.step_id = 1

            rolled = await planner.rollback_plan(plan)
            assert rolled.steps[0].status == StepStatus.DONE
            assert rolled.steps[0].result == "步骤1完成"


class TestPlannerPropagateFailure:
    @pytest.mark.asyncio
    async def test_propagate_failure_marks_plan_failed(self, planner):
        plan = await planner.create_plan("传播失败", session_id="rb6")
        result = await planner.propagate_failure(plan, "执行出错")
        assert result is None
        assert plan.status == PlanStatus.FAILED

    @pytest.mark.asyncio
    async def test_propagate_failure_returns_parent(self, store, llm):
        planner = Planner(store=store, llm=llm)
        parent = await planner.create_plan("父计划", session_id="rb7")
        child = await planner.create_plan("子计划", session_id="rb7")

        await store.update(
            "plans",
            data={"parent_plan_id": parent.plan_id},
            conditions={"id": child.plan_id},
        )
        child.parent_plan_id = parent.plan_id

        result = await planner.propagate_failure(child, "子计划失败")
        assert result is not None
        assert result.plan_id == parent.plan_id
        assert child.status == PlanStatus.FAILED

    @pytest.mark.asyncio
    async def test_propagate_failure_no_parent_returns_none(self, planner):
        plan = await planner.create_plan("无父计划", session_id="rb8")
        result = await planner.propagate_failure(plan, "失败原因")
        assert result is None