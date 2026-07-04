import json
from src.models.plan import Step, StepStatus, ActionType, RollbackSnapshot, Plan, PlanStatus


class TestStep:
    def test_create_step(self):
        step = Step(step_id=1, description="Search the web")
        assert step.step_id == 1
        assert step.description == "Search the web"
        assert step.status == StepStatus.PENDING
        assert step.action == ActionType.LLM_CALL
        assert step.dependencies == []
        assert step.timeout_seconds == 60
        assert step.result is None
        assert step.retry_count == 0
        assert step.max_retries == 3

    def test_step_with_tool_call(self):
        step = Step(
            step_id=2,
            description="Call web search",
            action=ActionType.TOOL_CALL,
            dependencies=[1],
            timeout_seconds=30,
        )
        assert step.action == ActionType.TOOL_CALL
        assert step.dependencies == [1]

    def test_step_status_values(self):
        assert StepStatus.PENDING == "pending"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.DONE == "done"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.SKIPPED == "skipped"

    def test_action_type_values(self):
        assert ActionType.TOOL_CALL == "tool_call"
        assert ActionType.LLM_CALL == "llm_call"
        assert ActionType.SUB_PLAN == "sub_plan"


class TestRollbackSnapshot:
    def test_create_rollback_snapshot(self):
        snapshot = RollbackSnapshot()
        assert snapshot.step_id == 0
        assert snapshot.completed_steps_results == {}
        assert snapshot.working_memory_keys == []
        assert snapshot.tool_context == {}

    def test_rollback_snapshot_with_data(self):
        snapshot = RollbackSnapshot(
            step_id=3,
            completed_steps_results={1: "result1", 2: "result2"},
            working_memory_keys=["key1"],
            tool_context={"tool": "web_search"},
        )
        assert snapshot.step_id == 3
        assert snapshot.completed_steps_results[1] == "result1"


class TestPlan:
    def test_create_plan(self):
        plan = Plan(session_id="sess-001", goal="Search for Python async")
        assert plan.session_id == "sess-001"
        assert plan.goal == "Search for Python async"
        assert plan.plan_id is not None
        assert plan.parent_plan_id is None
        assert plan.priority == 5
        assert plan.status == PlanStatus.RUNNING
        assert plan.steps == []
        assert plan.created_at is not None
        assert plan.updated_at is not None

    def test_plan_with_steps(self):
        steps = [
            Step(step_id=1, description="Step 1"),
            Step(step_id=2, description="Step 2", dependencies=[1]),
        ]
        plan = Plan(session_id="sess-001", goal="Test", steps=steps)
        assert len(plan.steps) == 2
        assert plan.steps[1].dependencies == [1]

    def test_plan_with_parent(self):
        plan = Plan(session_id="sess-001", goal="Sub task", parent_plan_id="parent-123")
        assert plan.parent_plan_id == "parent-123"

    def test_plan_status_values(self):
        assert PlanStatus.RUNNING == "running"
        assert PlanStatus.COMPLETED == "completed"
        assert PlanStatus.FAILED == "failed"
        assert PlanStatus.PAUSED == "paused"

    def test_plan_unique_ids(self):
        plan1 = Plan(session_id="sess-001", goal="Task 1")
        plan2 = Plan(session_id="sess-001", goal="Task 2")
        assert plan1.plan_id != plan2.plan_id

    def test_plan_touch_updates_updated_at(self):
        plan = Plan(session_id="sess-001", goal="Test")
        original_updated_at = plan.updated_at
        plan.touch()
        assert plan.updated_at != original_updated_at

    def test_plan_to_db_dict(self):
        steps = [Step(step_id=1, description="Step 1")]
        plan = Plan(session_id="sess-001", goal="Test", steps=steps)
        db_dict = plan.to_db_dict()
        assert db_dict["id"] == plan.plan_id
        assert db_dict["session_id"] == "sess-001"
        assert db_dict["goal"] == "Test"
        assert db_dict["status"] == "running"
        assert isinstance(db_dict["steps_json"], str)
        steps_data = json.loads(db_dict["steps_json"])
        assert len(steps_data) == 1
        assert steps_data[0]["step_id"] == 1

    def test_plan_to_db_dict_empty_steps(self):
        plan = Plan(session_id="sess-001", goal="Test")
        db_dict = plan.to_db_dict()
        assert db_dict["steps_json"] == "[]"
        assert db_dict["rollback_point_json"] is None

    def test_plan_from_db_row(self):
        steps_json = json.dumps([{"step_id": 1, "description": "Step 1", "status": "pending", "action": "llm_call", "dependencies": [], "timeout_seconds": 60, "result": None, "retry_count": 0, "max_retries": 3}])
        rollback_json = json.dumps({"step_id": 0, "completed_steps_results": {}, "working_memory_keys": [], "tool_context": {}})
        row = {
            "id": "plan-123",
            "parent_plan_id": None,
            "session_id": "sess-001",
            "goal": "Test goal",
            "priority": 5,
            "status": "running",
            "steps_json": steps_json,
            "rollback_point_json": rollback_json,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        plan = Plan.from_db_row(row)
        assert plan.plan_id == "plan-123"
        assert plan.session_id == "sess-001"
        assert plan.goal == "Test goal"
        assert len(plan.steps) == 1
        assert plan.steps[0].step_id == 1

    def test_plan_roundtrip(self):
        steps = [
            Step(step_id=1, description="Step 1"),
            Step(step_id=2, description="Step 2", action=ActionType.TOOL_CALL, dependencies=[1]),
        ]
        plan = Plan(session_id="sess-001", goal="Test", steps=steps)
        db_dict = plan.to_db_dict()
        restored = Plan.from_db_row(db_dict)
        assert restored.plan_id == plan.plan_id
        assert restored.session_id == plan.session_id
        assert restored.goal == plan.goal
        assert len(restored.steps) == 2
        assert restored.steps[1].action == ActionType.TOOL_CALL