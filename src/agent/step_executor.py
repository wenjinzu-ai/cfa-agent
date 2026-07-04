from __future__ import annotations

import json
import re

from src.agent.agent_context import AgentContext
from src.common.exceptions import PlanExecutionError
from src.common.logger import logger
from src.models.plan import Step, StepStatus, ActionType
from src.models.tool import ToolResult


_THOUGHT_RE = re.compile(r"Thought:\s*(.+?)(?=\n(?:Action|Final Answer)|$)", re.DOTALL)
_ACTION_RE = re.compile(r"Action:\s*(\w+)\((.+?)\)", re.DOTALL)
_FINAL_ANSWER_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)


class StepExecutor:
    def __init__(self, context: AgentContext):
        self._ctx = context

    async def execute_step(self, step: Step) -> Step:
        step.status = StepStatus.RUNNING
        try:
            if step.action == ActionType.TOOL_CALL:
                result = await self._execute_tool_step(step)
            elif step.action == ActionType.LLM_CALL:
                result = await self._execute_llm_step(step)
            elif step.action == ActionType.SUB_PLAN:
                result = await self._execute_sub_plan_step(step)
            else:
                raise PlanExecutionError(
                    message=f"未知的动作类型: {step.action}",
                    detail={"step_id": step.step_id, "action": step.action.value},
                )

            step.result = result.data if isinstance(result, ToolResult) else result
            step.status = StepStatus.DONE
            return step

        except Exception as e:
            step.status = StepStatus.FAILED
            step.result = {"error": str(e)}
            step.retry_count += 1
            logger.error(
                "步骤 %d 执行失败: %s (重试 %d/%d)",
                step.step_id, e, step.retry_count, step.max_retries,
            )
            if step.retry_count >= step.max_retries:
                raise PlanExecutionError(
                    message=f"步骤 {step.step_id} 执行失败，已达最大重试次数",
                    detail={"step_id": step.step_id, "error": str(e)},
                ) from e
            return step

    async def _execute_tool_step(self, step: Step) -> ToolResult:
        params = step.result if isinstance(step.result, dict) else {}
        if not params:
            params = await self._resolve_tool_params(step)

        guardrail_result = await self._ctx.guardrail_manager.check_input(
            json.dumps(params, ensure_ascii=False)
        )
        input_content = guardrail_result.sanitized_content or json.dumps(params, ensure_ascii=False)

        result = await self._ctx.tool_dispatcher.dispatch_with_retry(
            tool_name=self._extract_tool_name(step),
            params=json.loads(input_content) if input_content.startswith("{") else params,
        )

        output_text = result.data if result.success else (result.error or "")
        output_guardrail = await self._ctx.guardrail_manager.check_output(
            str(output_text) if not isinstance(output_text, str) else output_text
        )
        if output_guardrail.sanitized_content:
            result.data = output_guardrail.sanitized_content

        return result

    async def _execute_llm_step(self, step: Step) -> dict:
        self._ctx.add_message("user", step.description)
        messages = self._ctx.get_messages()

        reply = await self._ctx.llm.chat(messages, session_id=self._ctx.session_id)

        guardrail_result = await self._ctx.guardrail_manager.check_output(reply)
        final_reply = guardrail_result.sanitized_content or reply

        self._ctx.add_message("assistant", final_reply)

        parsed = self._parse_react_output(final_reply)
        if parsed.get("final_answer"):
            return {"type": "final_answer", "content": parsed["final_answer"]}

        if parsed.get("action"):
            tool_name = parsed["action"]
            tool_params = parsed.get("action_params", {})
            tool_result = await self._ctx.tool_dispatcher.dispatch_with_retry(
                tool_name=tool_name,
                params=tool_params,
            )
            observation = tool_result.data if tool_result.success else tool_result.error
            self._ctx.add_message("user", f"Observation: {observation}")
            return {
                "type": "tool_observation",
                "thought": parsed.get("thought", ""),
                "tool_name": tool_name,
                "tool_result": observation,
            }

        return {"type": "llm_response", "content": final_reply}

    async def _execute_sub_plan_step(self, step: Step) -> dict:
        from src.agent.plan_executor import PlanExecutor
        executor = PlanExecutor(self._ctx)
        sub_plan = await executor.create_and_execute(
            goal=step.description,
            session_id=self._ctx.session_id,
        )
        return {
            "type": "sub_plan",
            "plan_id": sub_plan.plan_id,
            "status": sub_plan.status.value,
            "result": sub_plan.steps[-1].result if sub_plan.steps else None,
        }

    def _extract_tool_name(self, step: Step) -> str:
        desc = step.description.lower()
        for tool_def in self._ctx.tool_dispatcher.registry.list_tools():
            if tool_def.name.lower() in desc:
                return tool_def.name
        parts = desc.split()
        return parts[0] if parts else "unknown"

    async def _resolve_tool_params(self, step: Step) -> dict:
        self._ctx.add_message("user", f"请为以下步骤生成工具参数：{step.description}")
        messages = self._ctx.get_messages()
        reply = await self._ctx.llm.chat(messages, session_id=self._ctx.session_id)
        try:
            json_match = re.search(r"\{[^}]+\}", reply, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return {"query": step.description}

    @staticmethod
    def _parse_react_output(text: str) -> dict:
        result: dict = {}

        thought_m = _THOUGHT_RE.search(text)
        if thought_m:
            result["thought"] = thought_m.group(1).strip()

        action_m = _ACTION_RE.search(text)
        if action_m:
            result["action"] = action_m.group(1).strip()
            try:
                result["action_params"] = json.loads(action_m.group(2).strip())
            except json.JSONDecodeError:
                result["action_params"] = {"query": action_m.group(2).strip()}

        final_m = _FINAL_ANSWER_RE.search(text)
        if final_m:
            result["final_answer"] = final_m.group(1).strip()

        return result