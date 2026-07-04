from pydantic import BaseModel, Field
from enum import Enum
from typing import Any
from datetime import datetime, timezone
import json
import uuid


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    SUB_PLAN = "sub_plan"


class Step(BaseModel):
    step_id: int
    description: str
    status: StepStatus = StepStatus.PENDING
    action: ActionType = ActionType.LLM_CALL
    dependencies: list[int] = Field(default_factory=list)
    timeout_seconds: int = 60
    result: Any | None = None
    retry_count: int = 0
    max_retries: int = 3


class RollbackSnapshot(BaseModel):
    step_id: int = 0
    completed_steps_results: dict[int, Any] = Field(default_factory=dict)
    working_memory_keys: list[str] = Field(default_factory=list)
    tool_context: dict[str, Any] = Field(default_factory=dict)


class PlanStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_plan_id: str | None = None
    session_id: str
    goal: str
    priority: int = 5
    status: PlanStatus = PlanStatus.RUNNING
    steps: list[Step] = Field(default_factory=list)
    rollback_point: RollbackSnapshot = Field(default_factory=RollbackSnapshot)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.plan_id,
            "parent_plan_id": self.parent_plan_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "priority": self.priority,
            "status": self.status.value,
            "steps_json": json.dumps([s.model_dump() for s in self.steps]),
            "rollback_point_json": json.dumps(self.rollback_point.model_dump()) if self.steps else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Plan":
        steps_data = json.loads(row["steps_json"]) if row.get("steps_json") else []
        rollback_data = json.loads(row["rollback_point_json"]) if row.get("rollback_point_json") else {}
        return cls(
            plan_id=row["id"],
            parent_plan_id=row.get("parent_plan_id"),
            session_id=row["session_id"],
            goal=row["goal"],
            priority=row.get("priority", 5),
            status=PlanStatus(row.get("status", "running")),
            steps=[Step(**s) for s in steps_data],
            rollback_point=RollbackSnapshot(**rollback_data),
            created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=row.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )