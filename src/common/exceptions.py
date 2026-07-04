class CFAAgentError(Exception):
    base_message: str = "CFA-Agent error"

    def __init__(self, message: str = "", detail: dict | None = None):
        self.message = message or self.base_message
        self.detail = detail or {}
        super().__init__(self.message)


class AgentMemoryError(CFAAgentError):
    base_message = "Memory operation failed"


class MemoryNotFoundError(AgentMemoryError):
    base_message = "Memory entry not found"


class MemoryRetrievalError(AgentMemoryError):
    base_message = "Memory retrieval failed"


class ToolError(CFAAgentError):
    base_message = "Tool execution failed"


class ToolNotFoundError(ToolError):
    base_message = "Tool not found"


class ToolExecutionError(ToolError):
    base_message = "Tool execution error"


class ToolTimeoutError(ToolError):
    base_message = "Tool execution timeout"


class ToolPermissionError(ToolError):
    base_message = "Tool permission denied"


class GuardrailError(CFAAgentError):
    base_message = "Guardrail check failed"


class InputGuardrailError(GuardrailError):
    base_message = "Input blocked by guardrail"


class OutputGuardrailError(GuardrailError):
    base_message = "Output blocked by guardrail"


class BehaviorGuardrailError(GuardrailError):
    base_message = "Behavior guardrail violation detected"


class PlanError(CFAAgentError):
    base_message = "Plan operation failed"


class PlanNotFoundError(PlanError):
    base_message = "Plan not found"


class PlanExecutionError(PlanError):
    base_message = "Plan execution failed"


class LLMError(CFAAgentError):
    base_message = "LLM call failed"


class LLMRateLimitError(LLMError):
    base_message = "LLM rate limit exceeded"


class ConfigurationError(CFAAgentError):
    base_message = "Configuration error"