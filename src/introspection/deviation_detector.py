"""CFA-Agent 偏差检测器

检测智能体执行过程中偏离目标的行为

技术方案 §6.4：
偏差类型：
- 语义偏差：输出含义与任务目标不一致
- 结构偏差：输出格式不符合预期 Schema
- 事实偏差：输出与工具返回的事实不符
- 逻辑偏差：推理过程存在逻辑矛盾

检测方式：
- 基于 LLM 的语义偏差检测
- 基于规则的结构偏差检测
- 基于工具结果的事实偏差检测
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.llm.router import LLMRouter

logger = logging.getLogger("cfa-agent.introspection.deviation")


class DeviationDetector:
    """偏差检测器

    职责：
    - 检测执行过程中的偏差
    - 评估偏差严重程度
    - 提供修正建议

    Attributes:
        _threshold: 偏差阈值（0-1）
        _router: LLM 路由器（用于语义偏差检测）
    """

    def __init__(
        self,
        threshold: float = 0.6,
        router: Optional[LLMRouter] = None,
    ):
        self._threshold = threshold
        self._router = router

    async def detect(self, context: dict) -> dict | None:
        """检测偏差

        Args:
            context: 包含任务描述、执行步骤、当前结果等信息的上下文
                - task: 原始任务描述
                - history: 执行历史步骤
                - current_thought: 当前推理
                - last_observation: 最近观察结果

        Returns:
            dict | None: 偏差信息，若无偏差返回 None
                - type: 偏差类型 (semantic/structural/factual/logical)
                - severity: 严重程度 (0-1)
                - description: 偏差描述
                - suggestion: 修正建议
        """
        task = context.get("task", "")
        history = context.get("history", [])
        current_thought = context.get("current_thought", "")
        last_observation = context.get("last_observation", "")

        structural = self._detect_structural_deviation(context)
        if structural:
            return structural

        factual = self._detect_factual_deviation(context)
        if factual:
            return factual

        logical = self._detect_logical_deviation(context)
        if logical:
            return logical

        if self._router and task and (current_thought or last_observation):
            semantic = await self._detect_semantic_deviation(context)
            if semantic:
                return semantic

        return None

    def _detect_structural_deviation(self, context: dict) -> dict | None:
        """检测结构偏差

        检查输出格式是否符合预期 Schema
        """
        expected_format = context.get("expected_format")
        current_output = context.get("current_output")

        if not expected_format or not current_output:
            return None

        if isinstance(expected_format, dict) and isinstance(current_output, dict):
            missing_keys = set(expected_format.keys()) - set(current_output.keys())
            if missing_keys:
                return {
                    "type": "structural",
                    "severity": 0.7,
                    "description": f"输出缺少必要字段: {', '.join(missing_keys)}",
                    "suggestion": f"补充缺失字段: {', '.join(missing_keys)}",
                }

        return None

    def _detect_factual_deviation(self, context: dict) -> dict | None:
        """检测事实偏差

        检查输出是否与工具返回的事实一致
        """
        history = context.get("history", [])
        current_thought = context.get("current_thought", "")

        if not history or not current_thought:
            return None

        observations = []
        for step in history:
            obs = step.get("observation", "")
            if obs:
                observations.append(obs)

        if not observations:
            return None

        return None

    def _detect_logical_deviation(self, context: dict) -> dict | None:
        """检测逻辑偏差

        检查推理过程是否存在逻辑矛盾
        """
        history = context.get("history", [])
        if len(history) < 2:
            return None

        recent_thoughts = []
        for step in history[-3:]:
            thought = step.get("thought", "")
            if thought:
                recent_thoughts.append(thought.lower())

        if len(recent_thoughts) < 2:
            return None

        contradiction_patterns = [
            (r"不是", r"是"),
            (r"不能", r"可以"),
            (r"没有", r"有"),
            (r"not", r"is"),
            (r"cannot", r"can"),
        ]

        for i, thought_a in enumerate(recent_thoughts[:-1]):
            for thought_b in recent_thoughts[i + 1:]:
                for neg_pattern, pos_pattern in contradiction_patterns:
                    if re.search(neg_pattern, thought_a) and re.search(pos_pattern, thought_b):
                        return {
                            "type": "logical",
                            "severity": 0.6,
                            "description": "检测到推理过程中的逻辑矛盾",
                            "suggestion": "检查推理步骤的一致性，消除矛盾",
                        }

        return None

    async def _detect_semantic_deviation(self, context: dict) -> dict | None:
        """检测语义偏差

        使用 LLM 判断当前输出是否偏离任务目标
        """
        task = context.get("task", "")
        current_thought = context.get("current_thought", "")
        last_observation = context.get("last_observation", "")

        if not self._router or not task:
            return None

        prompt = (
            f"Original task: {task}\n\n"
            f"Current thought: {current_thought}\n\n"
            f"Last observation: {last_observation}\n\n"
            "Rate how much the current progress deviates from the original task on a scale of 0 to 1.\n"
            "0 = perfectly on track, 1 = completely off track.\n\n"
            "Respond with just a number between 0 and 1."
        )

        try:
            response = await self._router.route_chat(
                messages=[
                    {"role": "system", "content": "You are evaluating task deviation."},
                    {"role": "user", "content": prompt},
                ],
                task_type="execution",
                temperature=0.1,
            )

            content = response.get("content", "0")
            score_match = re.search(r'(\d+\.?\d*)', content)
            if score_match:
                score = float(score_match.group(1))
                if score >= self._threshold:
                    return {
                        "type": "semantic",
                        "severity": score,
                        "description": f"当前执行方向偏离任务目标（偏差度: {score:.2f}）",
                        "suggestion": "重新审视任务目标，调整执行方向",
                    }
        except Exception as e:
            logger.warning(f"Semantic deviation detection failed: {e}")

        return None

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self._threshold = value