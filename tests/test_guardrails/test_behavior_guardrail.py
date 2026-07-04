import pytest

from src.guardrails.behavior_guardrail import BehaviorGuardrail
from src.models.guardrail import GuardrailAction, GuardrailSeverity


class TestBehaviorGuardrailStepLimit:
    @pytest.mark.asyncio
    async def test_under_step_limit_passes(self):
        rail = BehaviorGuardrail(max_steps=10)
        rail._step_count = 5
        result = await rail.check()
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_near_step_limit_warns(self):
        rail = BehaviorGuardrail(max_steps=10)
        rail._step_count = 9
        result = await rail.check()
        assert result.action == GuardrailAction.WARN
        assert result.rule_name == "step_limit"

    @pytest.mark.asyncio
    async def test_at_step_limit_blocked(self):
        rail = BehaviorGuardrail(max_steps=10)
        rail._step_count = 10
        result = await rail.check()
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "step_limit"
        assert result.severity == GuardrailSeverity.HIGH

    @pytest.mark.asyncio
    async def test_over_step_limit_blocked(self):
        rail = BehaviorGuardrail(max_steps=10)
        rail._step_count = 15
        result = await rail.check()
        assert result.action == GuardrailAction.BLOCK


class TestBehaviorGuardrailTokenBudget:
    @pytest.mark.asyncio
    async def test_under_budget_passes(self):
        rail = BehaviorGuardrail(token_budget=10000)
        rail._tokens_used = 5000
        result = await rail.check()
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_near_budget_warns(self):
        rail = BehaviorGuardrail(token_budget=10000)
        rail._tokens_used = 9000
        result = await rail.check()
        assert result.action == GuardrailAction.WARN
        assert result.rule_name == "token_budget"

    @pytest.mark.asyncio
    async def test_over_budget_blocked(self):
        rail = BehaviorGuardrail(token_budget=10000)
        rail._tokens_used = 12000
        result = await rail.check()
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "token_budget"


class TestBehaviorGuardrailDeviation:
    @pytest.mark.asyncio
    async def test_on_track_passes(self):
        rail = BehaviorGuardrail(deviation_threshold=0.2, consecutive_deviation_limit=3)
        rail.set_plan_goal("编写Python脚本")
        result = await rail.check("正在编写Python脚本")
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_slight_deviation_warns(self):
        rail = BehaviorGuardrail(deviation_threshold=0.8, consecutive_deviation_limit=5)
        rail.set_plan_goal("编写Python脚本实现数据分析")
        result = await rail.check("今天天气不错")
        assert result.action == GuardrailAction.WARN
        assert result.rule_name == "plan_deviation"

    @pytest.mark.asyncio
    async def test_consecutive_deviation_blocked(self):
        rail = BehaviorGuardrail(deviation_threshold=0.8, consecutive_deviation_limit=2)
        rail.set_plan_goal("编写Python脚本实现数据分析")
        rail._consecutive_deviations = 2
        result = await rail.check("今天天气不错")
        assert result.action == GuardrailAction.BLOCK
        assert result.rule_name == "plan_deviation"

    @pytest.mark.asyncio
    async def test_no_goal_skips_deviation_check(self):
        rail = BehaviorGuardrail()
        result = await rail.check("任意内容")
        assert result.action == GuardrailAction.PASS

    @pytest.mark.asyncio
    async def test_check_does_not_mutate_deviation_state(self):
        rail = BehaviorGuardrail(deviation_threshold=0.8, consecutive_deviation_limit=3)
        rail.set_plan_goal("编写Python脚本")
        assert rail._consecutive_deviations == 0
        await rail.check("今天天气不错")
        assert rail._consecutive_deviations == 0


class TestBehaviorGuardrailSimilarity:
    def test_identical_strings(self):
        sim = BehaviorGuardrail._compute_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self):
        sim = BehaviorGuardrail._compute_similarity("abc", "xyz")
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = BehaviorGuardrail._compute_similarity("hello world", "hello there")
        assert 0.0 < sim < 1.0

    def test_empty_goal(self):
        sim = BehaviorGuardrail._compute_similarity("", "hello")
        assert sim == 1.0

    def test_chinese_overlap(self):
        sim = BehaviorGuardrail._compute_similarity("编写Python脚本", "正在编写Python脚本")
        assert sim > 0.5

    def test_short_goal_substring_match(self):
        sim = BehaviorGuardrail._compute_similarity("ab", "abc")
        assert sim == 1.0

    def test_short_goal_no_match(self):
        sim = BehaviorGuardrail._compute_similarity("xy", "abc")
        assert sim == 0.0


class TestBehaviorGuardrailStateManagement:
    def test_record_step(self):
        rail = BehaviorGuardrail()
        assert rail._step_count == 0
        rail.record_step()
        rail.record_step()
        assert rail._step_count == 2

    def test_record_tokens(self):
        rail = BehaviorGuardrail()
        assert rail._tokens_used == 0
        rail.record_tokens(100)
        rail.record_tokens(50)
        assert rail._tokens_used == 150

    def test_record_deviation(self):
        rail = BehaviorGuardrail()
        rail.record_deviation(True)
        rail.record_deviation(True)
        assert rail._consecutive_deviations == 2
        rail.record_deviation(False)
        assert rail._consecutive_deviations == 0

    def test_reset(self):
        rail = BehaviorGuardrail()
        rail._step_count = 10
        rail._tokens_used = 5000
        rail._consecutive_deviations = 3
        rail._plan_goal = "test"
        rail.reset()
        assert rail._step_count == 0
        assert rail._tokens_used == 0
        assert rail._consecutive_deviations == 0
        assert rail._plan_goal == ""

    def test_set_plan_goal(self):
        rail = BehaviorGuardrail()
        rail.set_plan_goal("分析数据")
        assert rail._plan_goal == "分析数据"