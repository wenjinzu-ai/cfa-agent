from __future__ import annotations

from src.agent.agent_context import AgentContext
from src.agent.step_executor import StepExecutor
from src.common.exceptions import BehaviorGuardrailError
from src.common.logger import logger
from src.llm.prompt_manager import PromptManager
from src.models.plan import Plan, Step, StepStatus, PlanStatus, ActionType, RollbackSnapshot


class PlanExecutor:
    def __init__(self, ctx: AgentContext):
        self._ctx = ctx

    async def create_and_execute(self, goal: str, session_id: str) -> Plan:
        plan = await self._create_plan(goal, session_id)
        plan = await self._execute_plan(plan)
        return plan

    async def _create_plan(self, goal: str, session_id: str) -> Plan:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/cot",
            question=f"请将以下任务分解为具体步骤：\n{goal}",
        )
        try:
            from src.models.message import ChatMessage, Role

            chat_messages = [
                ChatMessage(
                    role=Role(m.get("role", "user")), content=m.get("content", "")
                )
                for m in messages
            ]
            response = await self._ctx.llm.chat(chat_messages)
            steps = self._parse_steps(response)
        except Exception as e:
            logger.warning("LLM 规划失败，使用单步回退: %s", e)
            steps = [Step(step_id=1, description=goal, action=ActionType.LLM_CALL)]

        plan = Plan(
            goal=goal,
            steps=steps,
            rollback_point=RollbackSnapshot(step_id=0, completed_steps_results={}),
        )
        plan_data = plan.to_db_dict()
        plan_data["id"] = plan.plan_id
        await self._ctx.working_memory.store.create_plan(plan_data)
        return plan

    async def _execute_plan(self, plan: Plan) -> Plan:
        step_executor = StepExecutor(self._ctx)
        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue
            step.status = StepStatus.RUNNING
            try:
                result = await step_executor.execute(step)
                step.status = StepStatus.DONE
                step.result = str(result.get("content", result))
            except BehaviorGuardrailError as e:
                logger.warning("行为护栏拦截: %s", e.message)
                step.status = StepStatus.FAILED
                step.result = f"行为护栏拦截: {e.message}"
                plan.status = PlanStatus.FAILED
                return plan
            except Exception as e:
                logger.warning("步骤 %d 执行失败: %s", step.step_id, e)
                step.status = StepStatus.FAILED
                step.result = str(e)
                if step.retry_count < step.max_retries:
                    step.retry_count += 1
                    step.status = StepStatus.PENDING
                else:
                    plan.status = PlanStatus.FAILED
                    return plan
        plan.status = PlanStatus.COMPLETED
        return plan

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