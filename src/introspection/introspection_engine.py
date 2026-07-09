"""CFA-Agent 内省引擎

协调内省系统的各个组件，驱动内省状态转换

技术方案 §6.2：
内省系统不是独立于 ReAct 的额外系统，而是对 ReAct 循环中状态感知能力的抽象描述。
内省状态机与 ReAct 工作流是同一件事的两种视角：
- 状态机描述「Agent 处于什么状态」
- ReAct 工作流描述「Agent 执行什么操作」
"""
from __future__ import annotations

import logging
from typing import Optional

from src.common.types import IntrospectionState
from src.introspection.confidence_estimator import ConfidenceEstimator
from src.introspection.deviation_detector import DeviationDetector
from src.introspection.health_checker import HealthChecker
from src.introspection.state_machine import IntrospectionStateMachine

logger = logging.getLogger("cfa-agent.introspection.engine")


class IntrospectionEngine:
    """内省引擎

    职责：
    - 驱动内省状态转换（与 ReAct 循环对齐）
    - 协调偏差检测、健康检查、置信度评估
    - 触发修正或告警
    - 为 ReAct 循环提供内省信息

    Attributes:
        _state_machine: 内省状态机
        _deviation_detector: 偏差检测器
        _confidence_estimator: 置信度评估器
        _health_checker: 健康检查器
    """

    def __init__(
        self,
        deviation_detector: Optional[DeviationDetector] = None,
        confidence_estimator: Optional[ConfidenceEstimator] = None,
        health_checker: Optional[HealthChecker] = None,
    ):
        self._state_machine = IntrospectionStateMachine()
        self._deviation_detector = deviation_detector or DeviationDetector()
        self._confidence_estimator = confidence_estimator or ConfidenceEstimator()
        self._health_checker = health_checker or HealthChecker()

    @property
    def current_state(self) -> IntrospectionState:
        return self._state_machine.state

    @property
    def state_machine(self) -> IntrospectionStateMachine:
        return self._state_machine

    async def transition(self, new_state: IntrospectionState) -> bool:
        """转换内省状态

        Args:
            new_state: 目标状态

        Returns:
            bool: 是否转换成功
        """
        success = self._state_machine.transition(new_state)
        if success:
            logger.debug(f"Introspection state transitioned to: {new_state.value}")
        else:
            logger.warning(f"Invalid state transition: {self._state_machine.state.value} → {new_state.value}")
        return success

    async def transition_to_react_node(self, node_name: str) -> bool:
        """根据 ReAct 节点名转换内省状态

        将 ReAct 节点名映射到内省状态

        Args:
            node_name: ReAct 节点名 (think/act/observe/reflect/answer)

        Returns:
            bool: 是否转换成功
        """
        node_to_state = {
            "think": IntrospectionState.THINKING,
            "act": IntrospectionState.ACTING,
            "observe": IntrospectionState.OBSERVING,
            "reflect": IntrospectionState.REFLECTING,
            "answer": IntrospectionState.ANSWERING,
        }

        target_state = node_to_state.get(node_name)
        if target_state:
            return await self.transition(target_state)
        return False

    async def check_health(self) -> dict:
        """执行健康检查

        Returns:
            dict: 健康状态报告
        """
        return {
            "state": self._state_machine.state.value,
            "state_history": [s.value for s in self._state_machine.history[-5:]],
            "healthy": True,
        }

    async def detect_deviation(self, context: dict) -> dict | None:
        """检测偏差

        Args:
            context: 执行上下文

        Returns:
            dict | None: 偏差信息
        """
        return await self._deviation_detector.detect(context)

    async def estimate_confidence(self, context: dict) -> float:
        """评估置信度

        Args:
            context: 执行上下文

        Returns:
            float: 置信度 [0, 1]
        """
        return await self._confidence_estimator.estimate(context)

    async def introspect(self, context: dict) -> dict:
        """执行完整的内省检查

        综合偏差检测、置信度评估、健康检查

        Args:
            context: 执行上下文

        Returns:
            dict: 内省报告
        """
        deviation = await self.detect_deviation(context)
        confidence = await self.estimate_confidence(context)
        health = await self.check_health()

        should_alert = False
        should_reflect = False

        if deviation and deviation.get("severity", 0) >= 0.7:
            should_reflect = True

        if self._confidence_estimator.is_low_confidence(confidence):
            should_reflect = True

        if deviation and deviation.get("severity", 0) >= 0.9:
            should_alert = True

        if confidence < 0.2:
            should_alert = True

        return {
            "state": self._state_machine.state.value,
            "deviation": deviation,
            "confidence": confidence,
            "confidence_level": self._confidence_estimator.get_confidence_level(confidence),
            "health": health,
            "should_reflect": should_reflect,
            "should_alert": should_alert,
        }

    def reset(self) -> None:
        """重置内省引擎"""
        self._state_machine.reset()