"""CFA-Agent AgentService 服务层

从 YAML 配置加载 Agent 定义，创建 Agent 实例，构建 ReActGraph。
替代原来 AgentRegistry 的硬编码角色管理。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from src.agents.config import AgentConfig

logger = logging.getLogger("cfa-agent.agents.service")


class AgentService:
    """Agent 服务

    职责：
    - 从 agents.yaml 加载 Agent 配置
    - 提供按 ID 查询 Agent 配置
    - 管理 Agent 配置的增删改查
    - 未来可扩展：从数据库动态加载配置

    Attributes:
        _configs: Agent ID → AgentConfig 的映射
    """

    def __init__(self, config_path: Optional[str] = None):
        self._configs: dict[str, AgentConfig] = {}
        if config_path:
            self._load_from_yaml(config_path)

    def _load_from_yaml(self, config_path: str) -> None:
        """从 YAML 文件加载 Agent 配置

        Args:
            config_path: YAML 配置文件路径

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Agent config file not found: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        agents_data = data.get("agents", {})
        if not agents_data:
            logger.warning("No agents defined in config file: %s", config_path)
            return

        for agent_id, agent_data in agents_data.items():
            config = AgentConfig(
                id=agent_id,
                name=agent_data.get("name", agent_id),
                system_prompt=agent_data.get("system_prompt", ""),
                think_prompt=agent_data.get("think_prompt", ""),
                tools=agent_data.get("tools", []),
                capabilities=agent_data.get("capabilities", []),
                enable_verify=agent_data.get("enable_verify", False),
                max_steps=agent_data.get("max_steps", 10),
                max_verify_retries=agent_data.get("max_verify_retries", 2),
                is_entry_point=agent_data.get("is_entry_point", False),
                default_timeout=agent_data.get("default_timeout", 30.0),
            )
            self._configs[agent_id] = config
            logger.info("Loaded agent config: id=%s, name=%s, entry=%s",
                        agent_id, config.name, config.is_entry_point)

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """获取 Agent 配置

        Args:
            agent_id: Agent 唯一标识

        Returns:
            AgentConfig 或 None
        """
        return self._configs.get(agent_id)

    def get_required(self, agent_id: str) -> AgentConfig:
        """获取 Agent 配置（必须存在）

        Args:
            agent_id: Agent 唯一标识

        Returns:
            AgentConfig

        Raises:
            KeyError: Agent 不存在
        """
        config = self._configs.get(agent_id)
        if config is None:
            raise KeyError(f"Agent not found: {agent_id}. Available: {list(self._configs.keys())}")
        return config

    def get_entry_point(self) -> Optional[AgentConfig]:
        """获取系统入口 Agent

        Returns:
            标记为 is_entry_point 的 Agent 配置，或 None
        """
        for config in self._configs.values():
            if config.is_entry_point:
                return config
        return None

    def get_entry_point_required(self) -> AgentConfig:
        """获取系统入口 Agent（必须存在）

        Returns:
            AgentConfig

        Raises:
            RuntimeError: 没有入口 Agent
        """
        config = self.get_entry_point()
        if config is None:
            raise RuntimeError("No entry point agent configured. Set is_entry_point=true for one agent.")
        return config

    def list_all(self) -> list[AgentConfig]:
        """获取所有 Agent 配置"""
        return list(self._configs.values())

    def list_ids(self) -> list[str]:
        """获取所有 Agent ID"""
        return list(self._configs.keys())

    def build_agent_list_description(self) -> str:
        """生成专家团队描述文本（用于 Supervisor 提示词动态注入）

        从每个 Agent 的 capabilities 字段生成可读的能力描述，
        新增 Agent 时无需手动更新 Supervisor 提示词。

        Returns:
            str: 格式化的专家团队描述
        """
        lines = []
        for config in self._configs.values():
            if config.is_entry_point:
                continue
            cap_lines = []
            for cap in config.capabilities:
                cap_lines.append(f"  · {cap}")
            if cap_lines:
                lines.append(f"- {config.id}（{config.name}）：")
                lines.extend(cap_lines)
            else:
                tools_str = ", ".join(config.tools) if config.tools else "无"
                lines.append(f"- {config.id}（{config.name}）：工具=[{tools_str}]")
        return "\n".join(lines)

    def register(self, config: AgentConfig) -> None:
        """动态注册 Agent 配置

        Args:
            config: Agent 配置
        """
        self._configs[config.id] = config
        logger.info("Registered agent: id=%s, name=%s", config.id, config.name)

    def unregister(self, agent_id: str) -> bool:
        """动态移除 Agent 配置

        Args:
            agent_id: Agent 唯一标识

        Returns:
            True 如果成功移除，False 如果不存在
        """
        if agent_id in self._configs:
            del self._configs[agent_id]
            logger.info("Unregistered agent: %s", agent_id)
            return True
        return False

    @property
    def size(self) -> int:
        return len(self._configs)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._configs


_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """获取全局 AgentService 单例"""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service


def init_agent_service(config_path: str) -> AgentService:
    """初始化全局 AgentService（启动时调用）

    Args:
        config_path: agents.yaml 配置文件路径

    Returns:
        AgentService 实例
    """
    global _agent_service
    _agent_service = AgentService(config_path)
    logger.info("AgentService initialized with %d agents from %s",
                _agent_service.size, config_path)
    return _agent_service