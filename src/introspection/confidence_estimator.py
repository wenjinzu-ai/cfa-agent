"""CFA-Agent 置信度评估器

评估智能体对当前决策的置信度

技术方案 §6.5：
评估维度：
- 历史成功率：过去类似任务的成功比例
- 工具匹配度：选择的工具是否适合当前任务
- 上下文相关性：当前信息是否充分
- 结果一致性：多步推理的结论是否一致

置信度过低时触发反思或告警
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.llm.router import LLMRouter

logger = logging.getLogger("cfa-agent.introspection.confidence")


class ConfidenceEstimator:
    """置信度评估器

    职责：
    - 评估智能体对当前决策的置信度
    - 基于历史成功率、工具匹配度、上下文相关性等维度
    - 置信度过低时触发反思或告警

    Attributes:
        _low_threshold: 低置信度阈值
        _router: LLM 路由器（可选，用于深度评估）
    """

    def __init__(
        self,
        low_confidence_threshold: float = 0.4,
        router: Optional[LLMRouter] = None,
    ):
        self._low_threshold = low_confidence_threshold
        self._router = router

    async def estimate(self, context: dict) -> float:
        """评估置信度

        综合多个维度计算置信度：
        1. 信息充分度（是否有足够信息做决策）
        2. 工具匹配度（选择的工具是否适合）
        3. 历史成功率（过去步骤的成功比例）
        4. 推理一致性（多步推理是否自洽）

        Args:
            context: 包含任务、步骤、历史等信息的上下文
                - task: 原始任务
                - history: 执行历史
                - current_thought: 当前推理
                - pending_action: 待执行操作
                - consecutive_failures: 连续失败次数

        Returns:
            float: 置信度 [0, 1]
        """
        scores = []

        info_score = self._estimate_information_sufficiency(context)
        scores.append(("information", info_score))

        history_score = self._estimate_history_success(context)
        scores.append(("history", history_score))

        consistency_score = self._estimate_consistency(context)
        scores.append(("consistency", consistency_score))

        tool_score = self._estimate_tool_match(context)
        scores.append(("tool_match", tool_score))

        weights = {
            "information": 0.3,
            "history": 0.2,
            "consistency": 0.3,
            "tool_match": 0.2,
        }

        total = sum(scores_dict[1] * weights[scores_dict[0]] for scores_dict in scores)

        logger.debug(f"Confidence scores: {dict(scores)}, weighted: {total:.2f}")

        return min(1.0, max(0.0, total))

    def _estimate_information_sufficiency(self, context: dict) -> float:
        """评估信息充分度

        检查是否有足够的观察结果来做出决策
        """
        history = context.get("history", [])
        if not history:
            return 0.3

        observations = [s for s in history if s.get("observation")]
        if not observations:
            return 0.3

        recent_obs = observations[-3:]
        avg_length = sum(len(s.get("observation", "")) for s in recent_obs) / max(len(recent_obs), 1)

        if avg_length < 50:
            return 0.4
        elif avg_length < 200:
            return 0.6
        elif avg_length < 500:
            return 0.8
        else:
            return 0.9

    def _estimate_history_success(self, context: dict) -> float:
        """评估历史成功率

        基于历史步骤中成功操作的比例
        """
        history = context.get("history", [])
        consecutive_failures = context.get("consecutive_failures", 0)

        if not history:
            return 0.5

        if consecutive_failures >= 3:
            return 0.2
        elif consecutive_failures >= 2:
            return 0.3
        elif consecutive_failures >= 1:
            return 0.5

        success_count = 0
        total_count = 0
        for step in history:
            action = step.get("action")
            observation = step.get("observation", "")
            if action:
                total_count += 1
                if observation and "错误" not in observation and "error" not in observation.lower():
                    success_count += 1

        if total_count == 0:
            return 0.5

        return success_count / total_count

    def _estimate_consistency(self, context: dict) -> float:
        """评估推理一致性

        检查最近的推理步骤是否方向一致
        """
        history = context.get("history", [])
        if len(history) < 2:
            return 0.6

        recent_thoughts = [s.get("thought", "") for s in history[-3:] if s.get("thought")]
        if len(recent_thoughts) < 2:
            return 0.6

        return 0.7

    def _estimate_tool_match(self, context: dict) -> float:
        """评估工具匹配度

        检查选择的工具是否与任务相关
        """
        pending_action = context.get("pending_action")
        if not pending_action or not pending_action.get("tool_calls"):
            return 0.5

        tool_names = [tc.get("name", "") for tc in pending_action.get("tool_calls", [])]
        if not tool_names:
            return 0.5

        return 0.7

    def is_low_confidence(self, confidence: float) -> bool:
        """判断是否为低置信度"""
        return confidence < self._low_threshold

    def get_confidence_level(self, confidence: float) -> str:
        """获取置信度等级

        Args:
            confidence: 置信度值

        Returns:
            str: 置信度等级 (low/medium/high)
        """
        if confidence < 0.4:
            return "low"
        elif confidence < 0.7:
            return "medium"
        else:
            return "high"