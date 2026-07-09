"""配置管理测试"""
from __future__ import annotations

from src.common.settings import get_config, clear_config_cache


class TestConfig:
    """配置管理单元测试"""

    def test_get_config_returns_singleton(self):
        """测试 get_config 返回单例"""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_config_has_llm_settings(self):
        """测试 LLM 配置存在"""
        config = get_config()
        assert hasattr(config, "llm")
        assert hasattr(config.llm, "api_key")
        assert hasattr(config.llm, "base_url")
        assert hasattr(config.llm, "model")

    def test_config_has_app_settings(self):
        """测试应用配置存在"""
        config = get_config()
        assert hasattr(config, "app")
        assert hasattr(config.app, "host")
        assert hasattr(config.app, "port")
        assert hasattr(config.app, "debug")

    def test_config_has_database_settings(self):
        """测试数据库配置存在"""
        config = get_config()
        assert hasattr(config, "database")
        assert hasattr(config.database, "db_path")

    def test_clear_config_cache(self):
        """测试清除配置缓存"""
        config1 = get_config()
        clear_config_cache()
        config2 = get_config()
        assert config1 is not config2
        clear_config_cache()  # 清理测试影响


class TestTypes:
    """类型定义测试"""

    def test_agent_role_enum(self):
        """测试智能体角色枚举（已废弃，保留向后兼容）"""
        from src.common.types import AgentRole
        assert AgentRole.PLANNER.value == "planner"
        assert AgentRole.EXECUTOR.value == "executor"
        assert AgentRole.REVIEWER.value == "reviewer"
        assert AgentRole.SUPERVISOR.value == "supervisor"

    def test_task_status_enum(self):
        """测试任务状态枚举"""
        from src.common.types import TaskStatus
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"

    def test_introspection_state_enum(self):
        """测试内省状态枚举"""
        from src.common.types import IntrospectionState
        assert IntrospectionState.THINKING.value == "thinking"
        assert IntrospectionState.ACTING.value == "acting"
        assert IntrospectionState.REFLECTING.value == "reflecting"