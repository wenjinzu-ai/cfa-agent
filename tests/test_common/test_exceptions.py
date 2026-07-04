import pytest
from src.common.exceptions import (
    CFAAgentError,
    AgentMemoryError,
    MemoryNotFoundError,
    MemoryRetrievalError,
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolPermissionError,
    GuardrailError,
    InputGuardrailError,
    OutputGuardrailError,
    BehaviorGuardrailError,
    PlanError,
    PlanNotFoundError,
    PlanExecutionError,
    LLMError,
    LLMRateLimitError,
    ConfigurationError,
)


class TestCFAAgentError:
    def test_default_message(self):
        err = CFAAgentError()
        assert err.message == "CFA-Agent error"
        assert err.detail == {}
        assert str(err) == "CFA-Agent error"

    def test_custom_message(self):
        err = CFAAgentError(message="custom error")
        assert err.message == "custom error"

    def test_with_detail(self):
        err = CFAAgentError(detail={"key": "value"})
        assert err.detail == {"key": "value"}

    def test_is_exception(self):
        with pytest.raises(CFAAgentError):
            raise CFAAgentError()


class TestAgentMemoryErrors:
    def test_memory_error_inherits(self):
        err = AgentMemoryError()
        assert isinstance(err, CFAAgentError)
        assert err.message == "Memory operation failed"

    def test_memory_not_found(self):
        err = MemoryNotFoundError()
        assert isinstance(err, AgentMemoryError)
        assert err.message == "Memory entry not found"

    def test_memory_retrieval_error(self):
        err = MemoryRetrievalError()
        assert isinstance(err, AgentMemoryError)
        assert err.message == "Memory retrieval failed"

    def test_no_shadow_builtin(self):
        import builtins
        assert builtins.MemoryError is not AgentMemoryError
        assert builtins.MemoryError is MemoryError


class TestToolErrors:
    def test_tool_error_inherits(self):
        err = ToolError()
        assert isinstance(err, CFAAgentError)
        assert err.message == "Tool execution failed"

    def test_tool_not_found(self):
        err = ToolNotFoundError(detail={"tool_name": "web_search"})
        assert isinstance(err, ToolError)
        assert err.message == "Tool not found"
        assert err.detail == {"tool_name": "web_search"}

    def test_tool_execution_error(self):
        err = ToolExecutionError(detail={"error": "timeout"})
        assert isinstance(err, ToolError)

    def test_tool_timeout_error(self):
        err = ToolTimeoutError(detail={"timeout": 30})
        assert isinstance(err, ToolError)

    def test_tool_permission_error(self):
        err = ToolPermissionError(detail={"tool_name": "code_runner"})
        assert isinstance(err, ToolError)


class TestGuardrailErrors:
    def test_guardrail_error_inherits(self):
        err = GuardrailError()
        assert isinstance(err, CFAAgentError)
        assert err.message == "Guardrail check failed"

    def test_input_guardrail_error(self):
        err = InputGuardrailError(detail={"pattern": "ignore instructions"})
        assert isinstance(err, GuardrailError)
        assert err.message == "Input blocked by guardrail"

    def test_output_guardrail_error(self):
        err = OutputGuardrailError()
        assert isinstance(err, GuardrailError)

    def test_behavior_guardrail_error(self):
        err = BehaviorGuardrailError()
        assert isinstance(err, GuardrailError)


class TestPlanErrors:
    def test_plan_error_inherits(self):
        err = PlanError()
        assert isinstance(err, CFAAgentError)

    def test_plan_not_found(self):
        err = PlanNotFoundError()
        assert isinstance(err, PlanError)

    def test_plan_execution_error(self):
        err = PlanExecutionError(detail={"step_id": 3})
        assert isinstance(err, PlanError)


class TestLLMErrors:
    def test_llm_error_inherits(self):
        err = LLMError()
        assert isinstance(err, CFAAgentError)

    def test_llm_rate_limit_error(self):
        err = LLMRateLimitError()
        assert isinstance(err, LLMError)


class TestConfigurationError:
    def test_configuration_error_inherits(self):
        err = ConfigurationError()
        assert isinstance(err, CFAAgentError)