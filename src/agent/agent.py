from __future__ import annotations

import uuid

from src.agent.agent_context import AgentContext
from src.agent.plan_executor import PlanExecutor
from src.common.exceptions import InputGuardrailError, OutputGuardrailError
from src.common.logger import logger
from src.guardrails.guardrail_manager import GuardrailManager
from src.llm.base import BaseLLM
from src.memory.working_memory import WorkingMemory
from src.models.message import ChatResponse, ChatRequest
from src.tools.tool_dispatcher import ToolDispatcher


class Agent:
    def __init__(
        self,
        llm: BaseLLM,
        working_memory: WorkingMemory,
        tool_dispatcher: ToolDispatcher,
        guardrail_manager: GuardrailManager | None = None,
    ):
        self._llm = llm
        self._working_memory = working_memory
        self._tool_dispatcher = tool_dispatcher
        self._guardrail_manager = guardrail_manager or GuardrailManager()
        self._sessions: dict[str, AgentContext] = {}

    def _get_or_create_context(self, session_id: str) -> AgentContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = AgentContext(
                session_id=session_id,
                llm=self._llm,
                working_memory=self._working_memory,
                tool_dispatcher=self._tool_dispatcher,
                guardrail_manager=self._guardrail_manager,
            )
        return self._sessions[session_id]

    async def chat(self, request: ChatRequest) -> ChatResponse:
        session_id = request.session_id or str(uuid.uuid4())
        ctx = self._get_or_create_context(session_id)

        try:
            guardrail_result = await ctx.guardrail_manager.check_input(request.message)
            user_content = guardrail_result.sanitized_content or request.message
        except InputGuardrailError as e:
            logger.warning("输入被护栏拦截: %s", e.message)
            return ChatResponse(
                session_id=session_id,
                reply=f"抱歉，您的输入未通过安全检查：{e.message}",
            )

        ctx.add_message("user", user_content)

        executor = PlanExecutor(ctx)

        try:
            plan = await executor.create_and_execute(
                goal=user_content,
                session_id=session_id,
            )
        except Exception as e:
            logger.error("计划执行异常: %s", e)
            ctx.add_message("assistant", f"执行过程中出现错误：{e}")
            return ChatResponse(
                session_id=session_id,
                reply=f"执行过程中出现错误：{e}",
                steps_executed=0,
            )

        final_result = self._extract_final_result(plan)
        reply_text = str(final_result) if final_result else "任务已完成，但未生成明确结果。"

        try:
            output_guardrail = await ctx.guardrail_manager.check_output(reply_text)
            reply_text = output_guardrail.sanitized_content or reply_text
        except OutputGuardrailError as e:
            logger.warning("输出被护栏拦截: %s", e.message)
            reply_text = "抱歉，输出内容未通过安全检查，已过滤。"

        ctx.add_message("assistant", reply_text)

        steps_executed = sum(
            1 for s in plan.steps if s.status.value == "done"
        )

        return ChatResponse(
            session_id=session_id,
            reply=reply_text,
            plan_id=plan.plan_id,
            steps_executed=steps_executed,
        )

    async def chat_simple(self, message: str, session_id: str | None = None) -> str:
        request = ChatRequest(message=message, session_id=session_id or str(uuid.uuid4()))
        response = await self.chat(request)
        return response.reply

    def _extract_final_result(self, plan) -> str | None:
        for step in reversed(plan.steps):
            if step.status == "done" and step.result:
                if isinstance(step.result, dict):
                    if step.result.get("type") == "final_answer":
                        return step.result.get("content")
                    if step.result.get("type") == "llm_response":
                        return step.result.get("content")
                return str(step.result)
        return None

    def get_context(self, session_id: str) -> AgentContext | None:
        return self._sessions.get(session_id)

    def reset_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]