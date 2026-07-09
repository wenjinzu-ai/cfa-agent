"""CFA-Agent 内省状态机

与 ReAct 循环对齐的状态机定义：
sleeping → aware → thinking → acting → observing → answering
                                    ↓              ↑
                              reflecting → self_correcting
                                    ↓
                              alerting
"""
from __future__ import annotations

from src.common.types import IntrospectionState


VALID_TRANSITIONS: dict[IntrospectionState, set[IntrospectionState]] = {
    IntrospectionState.SLEEPING: {IntrospectionState.AWARE},
    IntrospectionState.AWARE: {IntrospectionState.THINKING, IntrospectionState.SLEEPING},
    IntrospectionState.THINKING: {
        IntrospectionState.ACTING,
        IntrospectionState.ANSWERING,
        IntrospectionState.REFLECTING,
    },
    IntrospectionState.ACTING: {IntrospectionState.OBSERVING},
    IntrospectionState.OBSERVING: {
        IntrospectionState.THINKING,
        IntrospectionState.REFLECTING,
        IntrospectionState.ANSWERING,
    },
    IntrospectionState.REFLECTING: {
        IntrospectionState.SELF_CORRECTING,
        IntrospectionState.ALERTING,
        IntrospectionState.THINKING,
    },
    IntrospectionState.SELF_CORRECTING: {IntrospectionState.THINKING},
    IntrospectionState.ALERTING: {IntrospectionState.SLEEPING},
    IntrospectionState.ANSWERING: {IntrospectionState.SLEEPING},
}


class IntrospectionStateMachine:
    """内省状态机

    职责：
    - 定义合法的状态转换路径
    - 校验状态转换合法性
    - 记录状态转换历史
    """

    def __init__(self):
        self._state = IntrospectionState.SLEEPING
        self._history: list[IntrospectionState] = [self._state]

    @property
    def state(self) -> IntrospectionState:
        return self._state

    def can_transition(self, target: IntrospectionState) -> bool:
        """检查是否可以转换到目标状态"""
        allowed = VALID_TRANSITIONS.get(self._state, set())
        return target in allowed

    def transition(self, target: IntrospectionState) -> bool:
        """执行状态转换

        Returns:
            bool: 转换是否成功
        """
        if not self.can_transition(target):
            return False
        self._state = target
        self._history.append(target)
        return True

    def reset(self) -> None:
        """重置到初始状态"""
        self._state = IntrospectionState.SLEEPING
        self._history = [self._state]

    @property
    def history(self) -> list[IntrospectionState]:
        return list(self._history)