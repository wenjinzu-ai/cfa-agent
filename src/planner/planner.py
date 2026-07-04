from __future__ import annotations

import json

from src.common.logger import logger
from src.llm.base import BaseLLM
from src.llm.prompt_manager import PromptManager
from src.memory.sqlite_store import SQLiteStore
from src.models.plan import ActionType, Plan, PlanStatus, RollbackSnapshot, Step, StepStatus


class Planner:
    def __init__(self, store: SQLiteStore, llm: BaseLLM):
        self._store = store
        self._llm = llm

    async def create_plan(self, goal: str, session_id: str) -> Plan:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/cot",
            question=f"请将以下目标分解为可执行的步骤列表，每步一行：\n{goal}",
        )
        try:
            from src.models.message import ChatMessage, Role
            chat_messages = [
                ChatMessage(role=Role(m.get("role", "user")), content=m.get("content", ""))
                for m in messages
            ]
            response = await self._llm.chat(chat_messages)
            steps = self._parse_steps(response)
        except Exception as e:
            logger.warning("LLM 规划失败，使用单步 Plan: %s", e)
            steps = [Step(step_id=1, description=goal, action=ActionType.LLM_CALL)]

        plan = Plan(session_id=session_id, goal=goal, steps=steps)
        plan.rollback_point = RollbackSnapshot(
            step_id=0,
            completed_steps_results={},
            working_memory_keys=[],
        )

        plan_data = plan.to_db_dict()
        await self._store.create_plan(plan_data)

        logger.info("计划创建完成: %s (共 %d 步骤)", plan.plan_id[:8], len(plan.steps))
        return plan

    async def update_step(
        self, plan: Plan, step_id: int, status: StepStatus, result: str | None = None
    ) -> Plan:
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = status
                if result is not None:
                    step.result = result
                break
        plan.touch()
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, plan.status.value, steps_json)
        return plan

    async def complete_plan(self, plan: Plan) -> Plan:
        plan.status = PlanStatus.COMPLETED
        plan.touch()
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, PlanStatus.COMPLETED.value, steps_json)
        return plan

    async def fail_plan(self, plan: Plan, reason: str) -> Plan:
        plan.status = PlanStatus.FAILED
        plan.touch()
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, PlanStatus.FAILED.value, steps_json)
        return plan

    async def get_next_step(self, plan: Plan) -> Step | None:
        for step in plan.steps:
            if step.status == StepStatus.PENDING:
                return step
        return None

    async def get_plan(self, plan_id: str) -> Plan | None:
        row = await self._store.find_one("plans", conditions={"id": plan_id})
        if row is None:
            return None
        return Plan.from_db_row(row)

    async def rollback_step(self, plan: Plan, failed_step_id: int) -> Plan:
        target_step: Step | None = None
        for step in plan.steps:
            if step.step_id == failed_step_id:
                step.status = StepStatus.PENDING
                step.retry_count += 1
                step.result = None
                target_step = step
                break
        plan.rollback_point.step_id = max(0, failed_step_id - 1)
        completed = {
            s.step_id: s.result
            for s in plan.steps
            if s.status == StepStatus.DONE and s.result is not None
        }
        plan.rollback_point.completed_steps_results = completed
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        rollback_json = json.dumps(plan.rollback_point.model_dump(), ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, plan.status.value, steps_json)
        await self._store.execute_write(
            "UPDATE plans SET rollback_point_json = ? WHERE id = ?",
            (rollback_json, plan.plan_id),
        )
        retry_count = target_step.retry_count if target_step else 0
        logger.info("步骤 %d 已回滚，重试次数 %d", failed_step_id, retry_count)
        return plan

    async def rollback_plan(self, plan: Plan) -> Plan:
        snapshot = plan.rollback_point
        for step in plan.steps:
            if step.step_id > snapshot.step_id:
                step.status = StepStatus.PENDING
                step.result = None
                step.retry_count = 0
        plan.touch()
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, plan.status.value, steps_json)
        logger.info("计划 %s 已回滚到步骤 %d", plan.plan_id[:8], snapshot.step_id)
        return plan

    async def propagate_failure(self, plan: Plan, reason: str) -> Plan | None:
        plan.status = PlanStatus.FAILED
        plan.touch()
        steps_json = json.dumps([s.model_dump() for s in plan.steps], ensure_ascii=False)
        await self._store.update_plan_status(plan.plan_id, PlanStatus.FAILED.value, steps_json)
        if plan.parent_plan_id:
            parent_row = await self._store.find_one(
                "plans", conditions={"id": plan.parent_plan_id}
            )
            if parent_row:
                logger.info(
                    "子计划 %s 失败已传播到父计划 %s",
                    plan.plan_id[:8],
                    plan.parent_plan_id[:8],
                )
                return Plan.from_db_row(parent_row)
        logger.info("计划 %s 失败: %s", plan.plan_id[:8], reason)
        return None

    def _parse_steps(self, llm_response: str) -> list[Step]:
        lines = [ln.strip() for ln in llm_response.strip().split("\n") if ln.strip()]
        steps = []
        for i, line in enumerate(lines, 1):
            cleaned = line.lstrip("0123456789.-) ")
            if cleaned:
                steps.append(Step(step_id=i, description=cleaned, action=ActionType.LLM_CALL))
        if not steps:
            steps.append(Step(step_id=1, description="执行任务", action=ActionType.LLM_CALL))
        return steps