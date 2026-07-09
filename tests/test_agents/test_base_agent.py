"""AgentConfig 和 AgentService 测试

重构后 Agent 由配置驱动，不再使用 BaseAgent/AgentRole/AgentRegistry。
"""
from __future__ import annotations

import tempfile
import yaml

import pytest

from src.agents.config import AgentConfig
from src.agents.service import AgentService, init_agent_service


class TestAgentConfig:
    """AgentConfig 数据类测试"""

    def test_create_minimal_config(self):
        config = AgentConfig(
            id="test-agent",
            name="Test Agent",
            system_prompt="You are a test agent.",
        )
        assert config.id == "test-agent"
        assert config.name == "Test Agent"
        assert config.system_prompt == "You are a test agent."
        assert config.think_prompt == ""
        assert config.tools == []
        assert config.enable_verify is False
        assert config.max_steps == 10
        assert config.max_verify_retries == 2
        assert config.is_entry_point is False
        assert config.default_timeout == 30.0

    def test_create_full_config(self):
        config = AgentConfig(
            id="supervisor",
            name="Supervisor",
            system_prompt="You are a supervisor.",
            think_prompt="Task: {task}",
            tools=["web_search", "delegate"],
            enable_verify=True,
            max_steps=15,
            max_verify_retries=3,
            is_entry_point=True,
            default_timeout=60.0,
        )
        assert config.id == "supervisor"
        assert config.tools == ["web_search", "call_agent"]
        assert config.enable_verify is True
        assert config.max_steps == 15
        assert config.is_entry_point is True
        assert config.default_timeout == 60.0

    def test_config_equality(self):
        a = AgentConfig(id="agent", name="A", system_prompt="hello")
        b = AgentConfig(id="agent", name="A", system_prompt="hello")
        assert a == b

    def test_config_inequality(self):
        a = AgentConfig(id="agent", name="A", system_prompt="hello")
        b = AgentConfig(id="agent", name="B", system_prompt="hello")
        assert a != b


class TestAgentService:
    """AgentService 测试"""

    def test_empty_service(self):
        service = AgentService()
        assert service.size == 0
        assert service.list_ids() == []
        assert service.get("nonexistent") is None

    def test_register_and_get(self):
        service = AgentService()
        config = AgentConfig(id="planner", name="Planner", system_prompt="You are a planner.")
        service.register(config)

        assert service.size == 1
        retrieved = service.get("planner")
        assert retrieved is config
        assert retrieved.name == "Planner"

    def test_register_duplicate_overwrites(self):
        service = AgentService()
        config1 = AgentConfig(id="agent", name="First", system_prompt="v1")
        config2 = AgentConfig(id="agent", name="Second", system_prompt="v2")
        service.register(config1)
        service.register(config2)

        assert service.size == 1
        assert service.get("agent").name == "Second"

    def test_unregister(self):
        service = AgentService()
        config = AgentConfig(id="agent", name="Agent", system_prompt="...")
        service.register(config)
        assert service.size == 1

        removed = service.unregister("agent")
        assert removed is config
        assert service.size == 0
        assert service.get("agent") is None

    def test_unregister_nonexistent(self):
        service = AgentService()
        removed = service.unregister("nonexistent")
        assert removed is None

    def test_list_ids(self):
        service = AgentService()
        service.register(AgentConfig(id="a", name="A", system_prompt="..."))
        service.register(AgentConfig(id="b", name="B", system_prompt="..."))
        ids = service.list_ids()
        assert sorted(ids) == ["a", "b"]

    def test_list_all(self):
        service = AgentService()
        config_a = AgentConfig(id="a", name="A", system_prompt="...")
        config_b = AgentConfig(id="b", name="B", system_prompt="...")
        service.register(config_a)
        service.register(config_b)

        all_configs = service.list_all()
        assert len(all_configs) == 2
        assert config_a in all_configs
        assert config_b in all_configs

    def test_get_entry_point(self):
        service = AgentService()
        service.register(AgentConfig(id="a", name="A", system_prompt="...", is_entry_point=False))
        service.register(AgentConfig(id="b", name="B", system_prompt="...", is_entry_point=True))
        service.register(AgentConfig(id="c", name="C", system_prompt="...", is_entry_point=False))

        entry = service.get_entry_point()
        assert entry is not None
        assert entry.id == "b"

    def test_get_entry_point_none(self):
        service = AgentService()
        service.register(AgentConfig(id="a", name="A", system_prompt="..."))
        entry = service.get_entry_point()
        assert entry is None

    def test_get_required(self):
        service = AgentService()
        config = AgentConfig(id="agent", name="Agent", system_prompt="...")
        service.register(config)

        retrieved = service.get_required("agent")
        assert retrieved is config

    def test_get_required_raises(self):
        service = AgentService()
        with pytest.raises(KeyError):
            service.get_required("nonexistent")

    def test_load_from_yaml(self):
        yaml_data = {
            "agents": {
                "supervisor": {
                    "name": "Supervisor",
                    "is_entry_point": True,
                    "enable_verify": True,
                    "max_steps": 10,
                    "tools": ["call_agent"],
                    "system_prompt": "You are the supervisor.",
                    "think_prompt": "Task: {task}",
                },
                "executor": {
                    "name": "Executor",
                    "tools": ["web_search"],
                    "system_prompt": "You are the executor.",
                },
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(yaml_data, f)
            tmp_path = f.name

        try:
            service = AgentService(tmp_path)
            assert service.size == 2

            supervisor = service.get("supervisor")
            assert supervisor is not None
            assert supervisor.name == "Supervisor"
            assert supervisor.is_entry_point is True
            assert supervisor.enable_verify is True
            assert supervisor.tools == ["call_agent"]

            executor = service.get("executor")
            assert executor is not None
            assert executor.name == "Executor"
            assert executor.is_entry_point is False
            assert executor.tools == ["web_search"]
        finally:
            import os
            os.unlink(tmp_path)

    def test_init_agent_service_singleton(self):
        service1 = init_agent_service()
        service2 = init_agent_service()
        assert service1 is service2


class TestAgentConfigIntegration:
    """AgentConfig 集成测试：验证与 ReActGraph 的兼容性"""

    def test_config_for_supervisor(self):
        config = AgentConfig(
            id="supervisor",
            name="Supervisor",
            system_prompt="You are the supervisor.",
            think_prompt="Task: {task}",
            tools=["delegate"],
            enable_verify=True,
            max_steps=10,
            max_verify_retries=2,
            is_entry_point=True,
            default_timeout=30.0,
        )

        assert config.is_entry_point is True
        assert config.enable_verify is True
        assert "delegate" in config.tools
        assert config.max_steps == 10
        assert config.max_verify_retries == 2

    def test_config_for_planner(self):
        config = AgentConfig(
            id="planner",
            name="Planner",
            system_prompt="You are a planner.",
            tools=["web_search", "file_ops"],
            enable_verify=False,
            max_steps=5,
        )

        assert config.is_entry_point is False
        assert config.enable_verify is False
        assert config.max_steps == 5
        assert "web_search" in config.tools