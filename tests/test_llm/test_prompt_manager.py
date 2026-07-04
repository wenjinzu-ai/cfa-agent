import pytest
from pathlib import Path
from unittest.mock import patch

from src.llm.prompt_manager import PromptManager, _safe_format


@pytest.fixture(autouse=True)
def reset_prompt_manager():
    PromptManager._instance = None
    yield
    PromptManager._instance = None


class TestSafeFormat:
    def test_safe_format_replaces_known_vars(self):
        result = _safe_format("Hello {name}, welcome to {place}!", name="Alice", place="Wonderland")
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_safe_format_keeps_unknown_vars(self):
        result = _safe_format("Hello {name}, your {missing_var} is ready", name="Alice")
        assert result == "Hello Alice, your {missing_var} is ready"

    def test_safe_format_no_vars(self):
        result = _safe_format("No placeholders here")
        assert result == "No placeholders here"

    def test_safe_format_empty_string(self):
        result = _safe_format("")
        assert result == ""

    def test_safe_format_no_args(self):
        result = _safe_format("Hello {name}")
        assert result == "Hello {name}"

    def test_safe_format_extra_args_ignored(self):
        result = _safe_format("Hello {name}", name="Alice", extra="unused")
        assert result == "Hello Alice"


class TestPromptManagerSingleton:
    def test_get_instance_returns_same_object(self):
        a = PromptManager.get_instance()
        b = PromptManager.get_instance()
        assert a is b

    def test_get_instance_creates_instance(self):
        instance = PromptManager.get_instance()
        assert isinstance(instance, PromptManager)
        assert instance._loaded is False


class TestPromptManagerLoad:
    def test_load_all_from_default_dir(self):
        pm = PromptManager()
        pm.load_all()
        assert pm._loaded is True
        templates = pm.list_templates()
        assert len(templates) > 0

    def test_load_all_idempotent(self):
        pm = PromptManager()
        pm.load_all()
        count1 = len(pm.list_templates())
        pm.load_all()
        count2 = len(pm.list_templates())
        assert count1 == count2

    def test_load_missing_dir(self):
        pm = PromptManager()
        with patch("src.llm.prompt_manager.PROMPTS_DIR", Path("/nonexistent")):
            pm.load_all()
            assert pm._loaded is True
            assert len(pm.list_templates()) == 0


class TestPromptManagerGet:
    def test_get_system_agent_role(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("system/agent_role")
        assert "CFA-Agent" in system
        assert user == ""

    def test_get_safety_rules(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("system/safety_rules")
        assert "安全规则" in system

    def test_get_react_template(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("reasoning/react")
        assert "ReAct" in system
        assert "{question}" in user

    def test_get_cot_template(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("reasoning/cot")
        assert "Chain-of-Thought" in system

    def test_get_tool_call_template(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("tools/tool_call")
        assert "工具" in system

    def test_get_nonexistent_template(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get("nonexistent/template")
        assert system == ""
        assert user == ""


class TestPromptManagerVariableSubstitution:
    def test_get_with_variables(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get(
            "reasoning/react",
            question="What is Python?",
            tools_description="web_search, code_runner",
            relevant_memory="No relevant memory",
        )
        assert "What is Python?" in user
        assert "web_search, code_runner" in user
        assert "No relevant memory" in user

    def test_get_with_partial_variables_no_keyerror(self):
        pm = PromptManager()
        pm.load_all()
        system, user = pm.get(
            "reasoning/react",
            question="What is Python?",
        )
        assert "What is Python?" in user
        assert "{tools_description}" in user
        assert "{relevant_memory}" in user

    def test_get_system_prompt_only(self):
        pm = PromptManager()
        pm.load_all()
        system = pm.get_system_prompt("system/agent_role")
        assert "CFA-Agent" in system

    def test_get_user_prompt_only(self):
        pm = PromptManager()
        pm.load_all()
        user = pm.get_user_prompt("reasoning/cot", question="test question")
        assert "test question" in user


class TestPromptManagerBuildMessages:
    def test_build_messages_basic(self):
        pm = PromptManager()
        pm.load_all()
        messages = pm.build_messages("reasoning/cot", question="test")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_build_messages_with_history(self):
        pm = PromptManager()
        pm.load_all()
        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        messages = pm.build_messages("reasoning/cot", history=history, question="new question")
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"


class TestPromptManagerAutoLoad:
    def test_auto_load_on_get(self):
        pm = PromptManager()
        assert pm._loaded is False
        pm.get("system/agent_role")
        assert pm._loaded is True

    def test_auto_load_on_list(self):
        pm = PromptManager()
        assert pm._loaded is False
        pm.list_templates()
        assert pm._loaded is True


class TestPromptManagerReset:
    def test_reset_clears_state(self):
        pm = PromptManager()
        pm.load_all()
        assert pm._loaded is True
        assert len(pm._templates) > 0
        pm.reset()
        assert pm._loaded is False
        assert len(pm._templates) == 0