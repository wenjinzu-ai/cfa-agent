"""CFA-Agent ReAct 状态定义

基于 LangGraph TypedDict 定义 ReAct 循环的核心状态结构
所有字段与技术方案 §7.4 对齐
"""
from __future__ import annotations

import uuid
from typing import Optional, TypedDict


class Step(TypedDict):
    """单个步骤记录"""
    step_id: int
    thought: str
    action: Optional[dict]
    observation: Optional[str]
    duration_ms: Optional[int]


class PendingAction(TypedDict):
    """待执行的工具调用（标准 Function Calling 格式）"""
    tool_calls: list[dict]


class ReflectResult(TypedDict):
    """反思节点的输出"""
    should_continue: bool
    direction_correct: bool
    issues_found: list[str]
    suggestions: list[str]
    need_delegation: bool
    delegation_target: Optional[str]


class VerifyResult(TypedDict):
    """验证节点的输出"""
    passed: bool
    reason: str
    suggestions: list[str]


class VerifyHistoryEntry(TypedDict):
    """单次验证记录"""
    attempt: int
    passed: bool
    reason: str
    suggestions: list[str]


class StreamEvent(TypedDict, total=False):
    """流式事件（节点通过 stream_writer 推送）"""
    type: str
    node: str
    content: str
    agent: Optional[str]
    tool_name: Optional[str]
    tool_args: Optional[dict]
    observation: Optional[str]
    thought: Optional[str]
    step: Optional[int]
    duration_ms: Optional[int]


class ReActState(TypedDict, total=False):
    """ReAct 循环核心状态

    所有字段与技术方案 §7.4 一致：
    - task: 原始任务描述
    - context: 任务上下文（Planner 分解结果、会话历史等）
    - history: 完整的历史步骤
    - current_thought: 当前推理结果
    - pending_action: 待执行的工具调用
    - last_observation: 最近一次工具返回结果
    - reflect_result: 反思节点的输出
    - action_type: 当前路由决策类型
    - escalate: 是否需要升级到 Supervisor
    - step_count: 当前步数
    - max_steps: 最大步数限制
    - consecutive_reflect_count: 连续反思次数
    - context_overflow: 上下文窗口是否溢出
    - verify_result: 验证节点的输出
    - verify_count: 验证重试次数
    - verify_history: 验证历史记录
    - final_answer: 最终答案
    - user_question: 向用户提问的内容（ask_user 时使用）
    - user_reply: 用户回复内容
    - is_alerting: 是否处于告警状态
    - consecutive_failures: 连续失败次数
    """

    task: str
    context: dict
    history: list[Step]
    current_thought: str
    pending_action: Optional[PendingAction]
    last_observation: Optional[str]
    reflect_result: Optional[ReflectResult]
    verify_result: Optional[VerifyResult]
    verify_count: int
    verify_history: list[VerifyHistoryEntry]
    action_type: Optional[str]
    escalate: bool
    step_count: int
    max_steps: int
    consecutive_reflect_count: int
    context_overflow: bool
    final_answer: str
    user_question: Optional[str]
    user_reply: Optional[str]
    is_alerting: bool
    consecutive_failures: int
    intent: Optional[dict]


def create_initial_state(
    task: str,
    context: Optional[dict] = None,
    max_steps: int = 20,
) -> ReActState:
    """创建初始状态

    Args:
        task: 原始任务描述
        context: 初始上下文
        max_steps: 最大步数限制

    Returns:
        ReActState: 初始状态字典
    """
    return {
        "task": task,
        "context": context or {},
        "history": [],
        "current_thought": "",
        "pending_action": None,
        "last_observation": None,
        "reflect_result": None,
        "verify_result": None,
        "verify_count": 0,
        "verify_history": [],
        "action_type": None,
        "escalate": False,
        "step_count": 0,
        "max_steps": max_steps,
        "consecutive_reflect_count": 0,
        "context_overflow": False,
        "final_answer": "",
        "user_question": None,
        "user_reply": None,
        "is_alerting": False,
        "consecutive_failures": 0,
        "intent": None,
    }


def generate_step_id() -> int:
    """生成唯一步骤 ID"""
    return uuid.uuid4().int >> 96


def create_step(
    thought: str,
    action: Optional[dict] = None,
    observation: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Step:
    """创建新的步骤记录

    Args:
        thought: 推理内容
        action: 执行的动作（Function Calling 格式）
        observation: 观察结果
        duration_ms: 执行耗时

    Returns:
        Step: 步骤记录
    """
    return {
        "step_id": generate_step_id(),
        "thought": thought,
        "action": action,
        "observation": observation,
        "duration_ms": duration_ms,
    }