from __future__ import annotations

import json
from typing import AsyncIterator

from src.common.exceptions import (
    BehaviorGuardrailError,
    CFAAgentError,
    InputGuardrailError,
    ToolExecutionError,
)
from src.common.logger import logger
from src.core.perception import IntentType, PerceptionEngine
from src.core.reasoning import ReasoningEngine
from src.guardrails.behavior_guardrail import BehaviorGuardrail
from src.guardrails.guardrail_manager import GuardrailManager
from src.guardrails.input_guardrail import InputGuardrail
from src.guardrails.output_guardrail import OutputGuardrail
from src.guardrails.tool_guardrail import ToolGuardrail
from src.llm.base import BaseLLM
from src.llm.token_counter import TokenCounter
from src.memory.sqlite_store import SQLiteStore
from src.memory.working_memory import WorkingMemory
from src.models.message import (
    ChatRequest,
    ChatResponse,
    EventCategory,
    EventType,
    StreamEvent,
)
from src.models.plan import Plan, PlanStatus, Step, StepStatus
from src.planner.planner import Planner
from src.planner.reflector import Reflector
from src.tools.tool_dispatcher import ToolDispatcher


class Agent:
    def __init__(self, store: SQLiteStore, llm: BaseLLM):
        self._store = store
        self._llm = llm

        self._input_guardrail = InputGuardrail()
        self._output_guardrail = OutputGuardrail()
        self._tool_guardrail = ToolGuardrail()
        self._behavior_guardrail = BehaviorGuardrail()
        self._guardrail_manager = GuardrailManager(
            input_guardrail=self._input_guardrail,
            output_guardrail=self._output_guardrail,
            behavior_guardrail=self._behavior_guardrail,
        )

        self._perception = PerceptionEngine(store, self._guardrail_manager, llm=llm)
        self._reasoning = ReasoningEngine(llm)
        self._tool_dispatcher = ToolDispatcher()
        self._planner = Planner(store, llm)
        self._reflector = Reflector(store, llm)
        self._working_memory = WorkingMemory(store)
        self._token_counter = TokenCounter()

    @property
    def store(self) -> SQLiteStore:
        return self._store

    @property
    def behavior_guardrail(self) -> BehaviorGuardrail:
        return self._behavior_guardrail

    @property
    def guardrail_manager(self) -> GuardrailManager:
        return self._guardrail_manager

    async def run(self, request: ChatRequest) -> ChatResponse:
        try:
            context = await self._perception.perceive(request)
            intent = context.get("intent", IntentType.SIMPLE_QA)

            if intent in (IntentType.SIMPLE_CHAT, IntentType.SIMPLE_QA):
                return await self._run_direct(context)

            return await self._run_with_plan(context)

        except InputGuardrailError:
            return ChatResponse(
                session_id=request.session_id,
                reply="抱歉，您的输入被安全护栏拦截，请重新描述您的需求。",
                steps_executed=0,
            )

    async def _run_direct(self, context: dict) -> ChatResponse:
        session_id = context["session_id"]
        user_content = context["user_input"]

        reply = await self._reasoning.think_simple(
            {**context, "user_input": user_content},
        )

        output_result = await self._guardrail_manager.check_output(reply)
        sanitized = output_result.sanitized_content or reply

        await self._store.add_conversation_message(
            {"session_id": session_id, "role": "user", "content": context["original_input"]}
        )
        await self._store.add_conversation_message(
            {"session_id": session_id, "role": "assistant", "content": sanitized}
        )

        logger.info("直接回复 (intent=%s): %s", context.get("intent"), sanitized[:80])

        return ChatResponse(
            session_id=session_id,
            reply=sanitized,
            steps_executed=0,
            token_usage=self._token_counter.get_session_usage(session_id).to_dict(),
        )

    async def _run_with_plan(self, context: dict) -> ChatResponse:
        plan = await self._planner.create_plan(
            context["original_input"], context["session_id"]
        )
        self._behavior_guardrail.reset()
        self._behavior_guardrail.set_plan_goal(
            plan.goal, steps=[s.description for s in plan.steps]
        )

        await self._write_audit(
            plan_id=plan.plan_id,
            event_type="plan_update",
            event_category="decision",
            content=f"Plan created with {len(plan.steps)} steps",
        )

        steps_executed = 0

        while True:
            step = await self._planner.get_next_step(plan)
            if step is None:
                break

            self._behavior_guardrail.record_step()
            try:
                await self._guardrail_manager.check_behavior(step.description)
            except BehaviorGuardrailError as e:
                await self._write_audit(
                    plan_id=plan.plan_id,
                    event_type="error",
                    event_category="guardrail",
                    content=str(e.detail),
                )
                plan = await self._planner.fail_plan(plan, str(e.detail))
                break

            await self._write_audit(
                plan_id=plan.plan_id,
                step_id=step.step_id,
                event_type="thought",
                event_category="decision",
                content=step.description,
            )

            plan = await self._planner.update_step(
                plan, step.step_id, StepStatus.RUNNING
            )

            try:
                result = await self._execute_step(step, context, plan)
                plan = await self._planner.update_step(
                    plan, step.step_id, StepStatus.DONE, result
                )
                steps_executed += 1

                await self._write_audit(
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    event_type="observation",
                    event_category="tool_call",
                    content=result[:500],
                )

                await self._working_memory.set(
                    f"step_{step.step_id}_result", result
                )

            except ToolExecutionError as e:
                plan = await self._handle_step_failure(plan, step, str(e))
                if plan.status == PlanStatus.FAILED:
                    break

            except BehaviorGuardrailError as e:
                await self._write_audit(
                    plan_id=plan.plan_id,
                    event_type="error",
                    event_category="guardrail",
                    content=str(e.detail),
                )
                plan = await self._planner.fail_plan(plan, str(e.detail))
                break

            except CFAAgentError as e:
                plan = await self._planner.fail_plan(plan, str(e))
                break

        if plan.status == PlanStatus.RUNNING:
            plan = await self._planner.complete_plan(plan)

        final_result = await self._synthesize_result(plan, context)
        output_result = await self._guardrail_manager.check_output(final_result)
        sanitized = output_result.sanitized_content or final_result

        await self._store.add_conversation_message(
            {
                "session_id": context["session_id"],
                "role": "user",
                "content": context["original_input"],
            }
        )
        await self._store.add_conversation_message(
            {
                "session_id": context["session_id"],
                "role": "assistant",
                "content": sanitized,
            }
        )

        return ChatResponse(
            session_id=context["session_id"],
            reply=sanitized,
            plan_id=plan.plan_id,
            steps_executed=steps_executed,
            token_usage=self._token_counter.get_session_usage(
                context["session_id"]
            ).to_dict(),
        )

    async def run_stream(
        self, request: ChatRequest
    ) -> AsyncIterator[StreamEvent]:
        try:
            context = await self._perception.perceive(request)
            intent = context.get("intent", IntentType.SIMPLE_QA)

            if intent in (IntentType.SIMPLE_CHAT, IntentType.SIMPLE_QA):
                async for event in self._run_stream_direct(context):
                    yield event
                return

            async for event in self._run_stream_with_plan(context):
                yield event

        except InputGuardrailError:
            yield StreamEvent(
                event_type=EventType.ERROR,
                event_category=EventCategory.GUARDRAIL,
                content="输入被安全护栏拦截",
            )

    async def _run_stream_direct(self, context: dict) -> AsyncIterator[StreamEvent]:
        session_id = context["session_id"]
        full_content = ""

        try:
            async for event in self._reasoning.think_simple_stream(context):
                full_content += event.content
                yield event
        except Exception:
            reply = await self._reasoning.think_simple(context)
            full_content = reply
            yield StreamEvent(event_type=EventType.ANSWER, content=reply)

        output_result = await self._guardrail_manager.check_output(full_content)
        sanitized = output_result.sanitized_content or full_content

        await self._store.add_conversation_message(
            {"session_id": session_id, "role": "user", "content": context["original_input"]}
        )
        await self._store.add_conversation_message(
            {"session_id": session_id, "role": "assistant", "content": sanitized}
        )

    async def _run_stream_with_plan(self, context: dict) -> AsyncIterator[StreamEvent]:
        plan = await self._planner.create_plan(
            context["original_input"], context["session_id"]
        )
        self._behavior_guardrail.reset()
        self._behavior_guardrail.set_plan_goal(
            plan.goal, steps=[s.description for s in plan.steps]
        )

        yield StreamEvent(
            event_type=EventType.PLAN_UPDATE,
            event_category=EventCategory.DECISION,
            plan_id=plan.plan_id,
            content=f"Plan created: {plan.goal} ({len(plan.steps)} steps)",
        )

        while True:
            step = await self._planner.get_next_step(plan)
            if step is None:
                break

            self._behavior_guardrail.record_step()
            try:
                await self._guardrail_manager.check_behavior(step.description)
            except BehaviorGuardrailError as e:
                yield StreamEvent(
                    event_type=EventType.ERROR,
                    event_category=EventCategory.GUARDRAIL,
                    plan_id=plan.plan_id,
                    content=str(e.detail),
                )
                plan = await self._planner.fail_plan(plan, str(e.detail))
                break

            yield StreamEvent(
                event_type=EventType.THOUGHT,
                event_category=EventCategory.DECISION,
                plan_id=plan.plan_id,
                step_id=step.step_id,
                content=step.description,
            )

            plan = await self._planner.update_step(
                plan, step.step_id, StepStatus.RUNNING
            )

            try:
                result = await self._execute_step(step, context, plan)
                plan = await self._planner.update_step(
                    plan, step.step_id, StepStatus.DONE, result
                )

                yield StreamEvent(
                    event_type=EventType.OBSERVATION,
                    event_category=EventCategory.TOOL_CALL,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    content=result[:500],
                )

                await self._working_memory.set(
                    f"step_{step.step_id}_result", result
                )

            except ToolExecutionError as e:
                plan = await self._handle_step_failure(plan, step, str(e))
                if plan.status == PlanStatus.FAILED:
                    yield StreamEvent(
                        event_type=EventType.ERROR,
                        event_category=EventCategory.DECISION,
                        plan_id=plan.plan_id,
                        content=f"Plan failed: {e}",
                    )
                    break

            except BehaviorGuardrailError as e:
                yield StreamEvent(
                    event_type=EventType.ERROR,
                    event_category=EventCategory.GUARDRAIL,
                    plan_id=plan.plan_id,
                    content=str(e.detail),
                )
                plan = await self._planner.fail_plan(plan, str(e.detail))
                break

        if plan.status == PlanStatus.RUNNING:
            plan = await self._planner.complete_plan(plan)

        full_answer = ""
        async for event in self._synthesize_result_stream(plan, context):
            full_answer += event.content
            yield event

        output_result = await self._guardrail_manager.check_output(full_answer)
        sanitized = output_result.sanitized_content or full_answer

        await self._store.add_conversation_message(
            {
                "session_id": context["session_id"],
                "role": "user",
                "content": context["original_input"],
            }
        )
        await self._store.add_conversation_message(
            {
                "session_id": context["session_id"],
                "role": "assistant",
                "content": sanitized,
            }
        )

    async def _execute_step(
        self, step: Step, context: dict, plan: Plan
    ) -> str:
        if step.action.value == "tool_call":
            action = await self._reasoning.decide_action(
                step.description, context
            )
            tool_name = action.get("name", action.get("tool_name", ""))
            tool_params = action.get("parameters", action.get("params", {}))
            if tool_name:
                filtered_params = self._tool_guardrail.filter_sensitive_params(
                    tool_name, tool_params
                )
                result = await self._tool_dispatcher.dispatch_with_retry(
                    tool_name=tool_name, params=filtered_params
                )
                return result.data if result.success else f"工具调用失败: {result.error}"
            return json.dumps(action, ensure_ascii=False)

        elif step.action.value == "sub_plan":
            sub_plan = await self._planner.create_plan(
                step.description, context["session_id"]
            )
            sub_plan.parent_plan_id = plan.plan_id
            return f"子计划 {sub_plan.plan_id} 已创建"

        else:
            thought = await self._reasoning.think(
                {**context, "user_input": step.description},
                plan_id=plan.plan_id,
            )
            return thought

    async def _handle_step_failure(
        self, plan: Plan, step: Step, error_msg: str
    ) -> Plan:
        if step.retry_count < step.max_retries:
            logger.warning(
                "Step %d 失败，重试 %d/%d",
                step.step_id,
                step.retry_count + 1,
                step.max_retries,
            )
            plan = await self._planner.rollback_step(plan, step.step_id)
            return plan

        consecutive_failures = sum(
            1 for s in plan.steps if s.status == StepStatus.FAILED
        )
        if consecutive_failures >= 2 and plan.rollback_point.step_id > 0:
            logger.warning(
                "连续 %d 步失败，执行 Plan 级回滚", consecutive_failures
            )
            plan = await self._planner.rollback_plan(plan)
            return plan

        if plan.parent_plan_id:
            parent = await self._planner.propagate_failure(plan, error_msg)
            if parent:
                return parent

        plan = await self._planner.fail_plan(plan, error_msg)
        return plan

    async def _synthesize_result(self, plan: Plan, context: dict) -> str:
        if plan.status == PlanStatus.COMPLETED:
            completed_steps = [s for s in plan.steps if s.status == StepStatus.DONE and s.result]
            if len(completed_steps) == 1:
                return str(completed_steps[0].result)
            completed_results = [
                str(s.result) for s in completed_steps
            ]
            if completed_results:
                summary_input = (
                    f"原始目标：{plan.goal}\n\n"
                    f"执行结果：\n" + "\n".join(completed_results)
                    + "\n\n请根据以上执行结果，给出简洁的最终回答："
                )
                try:
                    return await self._reasoning.think(
                        {**context, "user_input": summary_input}
                    )
                except Exception:
                    return "\n".join(completed_results)
            return "任务已完成，但没有生成具体结果。"
        else:
            partial = [
                f"步骤 {s.step_id}: {s.description} → {str(s.result)[:200]}"
                for s in plan.steps
                if s.status == StepStatus.DONE and s.result
            ]
            msg = f"任务未能完全完成（状态：{plan.status.value}）。\n"
            if partial:
                msg += "已完成的部分结果：\n" + "\n".join(partial)
            return msg

    async def _synthesize_result_stream(
        self, plan: Plan, context: dict
    ) -> AsyncIterator[StreamEvent]:
        if plan.status == PlanStatus.COMPLETED:
            completed_steps = [s for s in plan.steps if s.status == StepStatus.DONE and s.result]
            if len(completed_steps) == 1:
                yield StreamEvent(
                    event_type=EventType.ANSWER,
                    plan_id=plan.plan_id,
                    content=str(completed_steps[0].result),
                )
                return

            completed_results = [str(s.result) for s in completed_steps]
            if completed_results:
                summary_input = (
                    f"原始目标：{plan.goal}\n\n"
                    f"执行结果：\n" + "\n".join(completed_results)
                    + "\n\n请根据以上执行结果，给出简洁的最终回答："
                )
                try:
                    async for event in self._reasoning.summarize_stream(summary_input):
                        event.plan_id = plan.plan_id
                        yield event
                    return
                except Exception:
                    yield StreamEvent(
                        event_type=EventType.ANSWER,
                        plan_id=plan.plan_id,
                        content="\n".join(completed_results),
                    )
                    return

            yield StreamEvent(
                event_type=EventType.ANSWER,
                plan_id=plan.plan_id,
                content="任务已完成，但没有生成具体结果。",
            )
        else:
            partial = [
                f"步骤 {s.step_id}: {s.description} → {str(s.result)[:200]}"
                for s in plan.steps
                if s.status == StepStatus.DONE and s.result
            ]
            msg = f"任务未能完全完成（状态：{plan.status.value}）。\n"
            if partial:
                msg += "已完成的部分结果：\n" + "\n".join(partial)
            yield StreamEvent(
                event_type=EventType.ANSWER,
                plan_id=plan.plan_id,
                content=msg,
            )

    async def _write_audit(
        self,
        plan_id: str,
        step_id: int | None = None,
        event_type: str = "",
        event_category: str = "",
        content: str = "",
    ) -> None:
        try:
            await self._store.write_audit_log(
                {
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "event_type": event_type,
                    "event_category": event_category,
                    "content": content,
                }
            )
        except Exception as e:
            logger.warning("审计日志写入失败: %s", e)