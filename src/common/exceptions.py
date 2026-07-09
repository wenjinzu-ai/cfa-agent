"""CFA-Agent 自定义异常"""
from __future__ import annotations


class CFAAgentError(Exception):
    """Base exception for all CFA-Agent errors"""


class ConfigurationError(CFAAgentError):
    """Configuration related error"""


class DatabaseError(CFAAgentError):
    """Database operation error"""


class AgentNotFoundError(CFAAgentError):
    """Agent not found error"""


class TaskNotFoundError(CFAAgentError):
    """Task not found error"""


class ToolNotFoundError(CFAAgentError):
    """Tool not found error"""


class ToolExecutionError(CFAAgentError):
    """Tool execution error"""


class MemoryError(CFAAgentError):
    """Memory system error"""


class LLMError(CFAAgentError):
    """LLM interaction error"""


class GuardrailViolationError(CFAAgentError):
    """Guardrail violation error"""


class MCPServerError(CFAAgentError):
    """MCP Server error"""


class ReActLoopError(CFAAgentError):
    """ReAct loop execution error"""


class DeviationDetectedError(CFAAgentError):
    """Deviation detected during execution"""