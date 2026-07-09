"""CFA-Agent 观察节点

observe 节点：结果格式化与上下文管理

技术方案 §7.5.3：
- 接收工具执行结果，格式化为标准 Observation
- 对长文本结果进行截断或摘要（避免上下文爆炸）
- 结构化非结构化数据
- 标记结果的可靠性和来源
- 上下文窗口管理：当历史步骤过多时，自动压缩早期步骤
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.llm.token_counter import TokenCounter
from src.loop_engine.state import ReActState, create_step

logger = logging.getLogger("cfa-agent.loop_engine.observe")


class ObserveNode:
    """观察节点

    职责：
    - 格式化工具执行结果
    - 管理上下文窗口（截断/摘要）
    - 将观察结果注入对话历史
    - 更新步数计数

    Attributes:
        _token_counter: Token 计数器
        _max_observation_length: 单条观察结果的最大长度
        _max_history_steps: 保留的最大历史步数
    """

    def __init__(
        self,
        token_counter: TokenCounter,
        max_observation_length: int = 2000,
        max_history_steps: int = 20,
    ):
        self._token_counter = token_counter
        self._max_observation_length = max_observation_length
        self._max_history_steps = max_history_steps

    async def execute(self, state: ReActState) -> dict:
        """处理观察结果

        Args:
            state: 当前状态（包含工具执行结果）

        Returns:
            dict: 更新后的状态（格式化后的观察结果）
        """
        logger.info(f"Observe node executing, processing step {state['step_count'] + 1}")

        observation = state.get("last_observation", "")
        current_thought = state.get("current_thought", "")
        pending_action = state.get("pending_action")

        formatted_observation = self._format_observation(observation)

        action_data = None
        if pending_action and pending_action.get("tool_calls"):
            action_data = {
                "tool_calls": pending_action["tool_calls"],
            }

        new_step = create_step(
            thought=current_thought,
            action=action_data,
            observation=formatted_observation,
        )

        history = state.get("history", [])
        history.append(new_step)

        if len(history) > self._max_history_steps:
            history = self._compress_history(history)

        messages = self._build_messages_from_history(history, state["task"])
        context_overflow = self._token_counter.is_overflow(messages)

        if context_overflow:
            logger.warning("Context overflow detected, compressing history")
            history = self._compress_history(history)

        return {
            "history": history,
            "step_count": state["step_count"] + 1,
            "last_observation": formatted_observation,
            "pending_action": None,
            "context_overflow": context_overflow,
            "consecutive_reflect_count": 0,
        }

    def _format_observation(self, observation: str) -> str:
        """格式化观察结果

        Args:
            observation: 原始观察结果

        Returns:
            str: 格式化后的观察结果
        """
        if not observation:
            return "(无观察结果)"

        if len(observation) > self._max_observation_length:
            truncated = observation[:self._max_observation_length]
            return f"{truncated}\n... (已截断，原长度 {len(observation)} 字符)"

        return observation

    def _compress_history(self, history: list) -> list:
        """压缩历史步骤

        保留最近的步骤，将早期步骤替换为摘要

        Args:
            history: 原始历史列表

        Returns:
            list: 压缩后的历史列表
        """
        if len(history) <= 5:
            return history

        recent = history[-5:]
        older = history[:-5]

        summary_parts = []
        for step in older:
            thought = step.get("thought", "")[:100]
            action = step.get("action", {})
            if action:
                action_str = json.dumps(action, ensure_ascii=False)[:100]
                summary_parts.append(f"Thought: {thought}, Action: {action_str}")
            elif thought:
                summary_parts.append(f"Thought: {thought}")

        summary = "早期步骤摘要:\n" + "\n".join(summary_parts)

        summary_step = create_step(
            thought=summary,
            action=None,
            observation=None,
        )

        return [summary_step] + recent

    def _build_messages_from_history(self, history: list, task: str) -> list[dict]:
        """从历史构建消息列表（用于 token 计数）

        Args:
            history: 历史步骤列表
            task: 原始任务

        Returns:
            list[dict]: 消息列表
        """
        messages = [
            {"role": "system", "content": f"Task: {task}"},
        ]

        for step in history:
            if step.get("thought"):
                messages.append({"role": "assistant", "content": step["thought"]})
            if step.get("observation"):
                messages.append({"role": "user", "content": step["observation"]})

        return messages

    async def handle_user_reply(self, state: ReActState) -> dict:
        """处理用户回复（ask_user 场景）

        Args:
            state: 当前状态（包含 user_reply）

        Returns:
            dict: 状态更新
        """
        user_reply = state.get("user_reply", "")
        if not user_reply:
            return state

        formatted_reply = f"用户回复: {user_reply}"

        new_step = create_step(
            thought=state.get("current_thought", "等待用户回复"),
            action=None,
            observation=formatted_reply,
        )

        history = state.get("history", [])
        history.append(new_step)

        return {
            "history": history,
            "step_count": state["step_count"] + 1,
            "last_observation": formatted_reply,
            "user_reply": None,
            "user_question": None,
        }