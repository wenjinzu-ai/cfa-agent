"""CFA-Agent 公共类型定义"""
from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    """智能体角色枚举

    .. deprecated::
        从 v0.2 开始，Agent 不再使用硬编码的角色枚举。
        改为配置驱动的 Agent ID（如 supervisor、planner、executor、reviewer）。
        请使用 AgentService.get(agent_id) 获取 AgentConfig。
    """
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    SUPERVISOR = "supervisor"


class AgentStatus(str, Enum):
    """智能体状态枚举"""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    SLEEPING = "sleeping"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IntrospectionState(str, Enum):
    """内省状态枚举 - 与 ReAct 循环对齐"""
    SLEEPING = "sleeping"
    AWARE = "aware"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    ANSWERING = "answering"
    REFLECTING = "reflecting"
    SELF_CORRECTING = "self_correcting"
    ALERTING = "alerting"


class MemoryType(str, Enum):
    """记忆类型枚举"""
    EPISODIC = "episodic"      # 情景记忆 - 记录成功的 ReAct 轨迹
    SEMANTIC = "semantic"       # 语义记忆 - 存储领域知识和概念
    PROCEDURAL = "procedural"   # 程序性记忆 - 存储成功策略和操作流程


class ToolSource(str, Enum):
    """工具来源枚举"""
    BUILTIN = "builtin"
    MCP = "mcp"


class ToolStatus(str, Enum):
    """工具状态枚举"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class ExecutionMode(str, Enum):
    """执行模式枚举"""
    SYNC = "sync"        # SSE 流式
    ASYNC = "async"      # 轮询查询


class SessionStatus(str, Enum):
    """会话状态枚举"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class MCPTransport(str, Enum):
    """MCP 传输协议枚举"""
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class MCPStatus(str, Enum):
    """MCP Server 状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class EventType(str, Enum):
    """事件类型枚举"""
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    FEEDBACK = "feedback"
    HEARTBEAT = "heartbeat"
    ALERT = "alert"
    DELEGATE = "delegate"
    BROADCAST = "broadcast"