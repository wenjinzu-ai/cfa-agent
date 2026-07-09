"""CFA-Agent 回答节点

answer 节点：汇总信息生成最终答案

技术方案 §7.5.5：
- 从历史步骤中提取关键信息
- 引用信息来源（增强可信度）
- 格式化输出（Markdown / 结构化 JSON）
- 标注置信度
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from src.llm.router import LLMRouter
from src.loop_engine.state import ReActState

logger = logging.getLogger("cfa-agent.loop_engine.answer")


class AnswerNode:
    """回答节点

    职责：
    - 汇总所有观察结果和推理过程
    - 生成最终答案
    - 格式化输出
    - 标注置信度和告警信息

    Attributes:
        _router: LLM 路由器（使用推理层模型）
    """

    def __init__(self, router: LLMRouter):
        self._router = router

    async def execute(self, state: ReActState) -> dict:
        """生成最终答案

        Args:
            state: 当前状态

        Returns:
            dict: 更新后的状态（包含最终答案）
        """
        logger.info("Answer node executing, generating final answer")

        if state.get("final_answer"):
            return self._finalize(state, state["final_answer"])

        messages = self._build_messages(state)

        try:
            response = await self._router.route_answer(messages=messages)
        except Exception as e:
            logger.error(f"LLM call failed in answer node: {e}")
            return self._finalize_from_history(state)

        content = response.get("content", "")
        if not content:
            return self._finalize_from_history(state)

        return self._finalize(state, content)

    def _build_messages(self, state: ReActState) -> list[dict]:
        """构建 answer 消息列表

        Args:
            state: 当前状态

        Returns:
            list[dict]: 消息列表
        """
        task = state["task"]
        history_text = self._format_history(state["history"])
        is_alerting = state.get("is_alerting", False)
        step_count = state["step_count"]
        max_steps = state["max_steps"]

        alert_note = ""
        if is_alerting:
            alert_note = "\n⚠️ 注意：此答案是在异常情况下生成的（如步数耗尽、死循环等），可能不完整。"

        prompt = (
            "Based on your analysis and observations, provide a final answer.\n\n"
            f"Original task:\n{task}\n\n"
            f"Steps taken ({step_count}/{max_steps}):\n{history_text}\n"
            f"{alert_note}\n"
            "Provide a clear, comprehensive answer that addresses the original task. "
            "If you couldn't fully complete the task, explain what you found and what's missing."
        )

        messages = [
            {"role": "system", "content": "You are an AI assistant providing a final answer based on your analysis."},
            {"role": "user", "content": prompt},
        ]

        return messages

    def _finalize(self, state: ReActState, answer: str) -> dict:
        """生成最终状态更新

        Args:
            state: 当前状态
            answer: 最终答案

        Returns:
            dict: 状态更新
        """
        return {
            "final_answer": answer,
            "action_type": "answer",
        }

    def _finalize_from_history(self, state: ReActState) -> dict:
        """从历史步骤中提取最终答案（LLM 调用失败时的降级方案）

        Args:
            state: 当前状态

        Returns:
            dict: 状态更新
        """
        observations = []
        for step in state.get("history", []):
            obs = step.get("observation", "")
            if obs and obs != "(无观察结果)":
                observations.append(obs)

        if observations:
            answer = "基于已收集的信息：\n\n" + "\n\n".join(observations[-3:])
        else:
            answer = "抱歉，无法完成任务。在执行过程中未能收集到足够的信息。"

        return {
            "final_answer": answer,
            "action_type": "answer",
            "is_alerting": True,
        }

    @staticmethod
    def _format_history(history: list) -> str:
        """格式化历史步骤"""
        if not history:
            return "(无历史步骤)"
        parts = []
        for i, step in enumerate(history[-5:]):
            thought = step.get("thought", "")
            obs = step.get("observation", "")
            parts.append(f"Step {i + 1}:")
            if thought:
                parts.append(f"  Thought: {thought[:200]}")
            if obs:
                parts.append(f"  Observation: {obs[:300]}")
        return "\n".join(parts)