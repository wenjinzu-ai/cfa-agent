"""CFA-Agent MCP 配置管理

管理 MCP Server 的连接配置
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.common.types import MCPStatus, MCPTransport
from src.db.repository.mcp_repo import MCPRepository


logger = logging.getLogger("cfa-agent.mcp.config")


class MCPConfigManager:
    """MCP 配置管理

    职责：
    - 加载 MCP Server 配置（config/mcp_servers.yaml）
    - 管理连接参数
    - 支持环境变量注入
    - 支持数据库持久化
    """

    def __init__(
        self,
        config_path: str | Path = "config/mcp_servers.yaml",
        repo: Optional[MCPRepository] = None,
    ):
        self._config_path = Path(config_path)
        self._repo = repo

    async def load_config(self) -> list[dict]:
        """加载 MCP Server 配置

        从 YAML 配置文件加载 Server 配置，并注入环境变量

        Returns:
            list[dict]: Server 配置列表
        """
        if not self._config_path.exists():
            logger.warning(f"MCP config file not found: {self._config_path}")
            return []

        try:
            with open(self._config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            servers = config.get("servers", [])
            processed_servers = []

            for server in servers:
                processed = self._process_server_config(server)
                processed_servers.append(processed)

            logger.info(f"Loaded {len(processed_servers)} MCP Server configs")
            return processed_servers

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return []

    def _process_server_config(self, server: dict) -> dict:
        """处理 Server 配置，注入环境变量

        Args:
            server: 原始 Server 配置

        Returns:
            dict: 处理后的配置
        """
        name = server.get("name", "")
        transport_str = server.get("transport", "stdio")
        config = server.get("config", {})
        env = config.get("env", {})

        processed_env = {}
        for key, value in env.items():
            if value == "" or value is None:
                env_value = os.environ.get(key, "")
                processed_env[key] = env_value
            else:
                processed_env[key] = value

        if processed_env:
            config["env"] = processed_env

        return {
            "name": name,
            "transport": MCPTransport(transport_str),
            "config": config,
            "enabled": server.get("enabled", True),
        }

    async def save_config(self, servers: list[dict]) -> None:
        """保存 MCP Server 配置到 YAML 文件

        Args:
            servers: Server 配置列表
        """
        config_data = {"servers": []}

        for server in servers:
            server_data = {
                "name": server.get("name", ""),
                "transport": server.get("transport", "stdio").value
                    if isinstance(server.get("transport"), MCPTransport)
                    else server.get("transport", "stdio"),
                "config": server.get("config", {}),
                "enabled": server.get("enabled", True),
            }
            config_data["servers"].append(server_data)

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Saved {len(servers)} MCP Server configs to {self._config_path}")

        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")
            raise

    async def load_from_database(self) -> list[dict]:
        """从数据库加载 MCP Server 配置

        Returns:
            list[dict]: Server 配置列表
        """
        if not self._repo:
            return []

        servers = await self._repo.get_all_servers()
        processed = []

        for server in servers:
            processed.append({
                "name": server["name"],
                "transport": MCPTransport(server["transport"]),
                "config": server.get("config", {}),
                "status": MCPStatus(server["status"]),
                "id": server["id"],
            })

        return processed

    async def save_to_database(self, server: dict) -> dict:
        """保存 Server 配置到数据库

        Args:
            server: Server 配置

        Returns:
            dict: 保存后的 Server 记录
        """
        if not self._repo:
            raise ValueError("Repository not initialized")

        return await self._repo.create_server(
            name=server["name"],
            transport=server["transport"],
            config=server.get("config"),
        )

    async def delete_from_database(self, name: str) -> bool:
        """从数据库删除 Server 配置

        Args:
            name: Server 名称

        Returns:
            bool: 是否成功删除
        """
        if not self._repo:
            raise ValueError("Repository not initialized")

        return await self._repo.delete_server(name)

    async def get_server_config(self, name: str) -> dict | None:
        """获取指定 Server 的配置

        Args:
            name: Server 名称

        Returns:
            dict | None: Server 配置
        """
        servers = await self.load_config()
        for server in servers:
            if server["name"] == name:
                return server

        if self._repo:
            server = await self._repo.get_server_by_name(name)
            if server:
                return {
                    "name": server["name"],
                    "transport": MCPTransport(server["transport"]),
                    "config": server.get("config", {}),
                    "status": MCPStatus(server["status"]),
                }

        return None

    async def merge_configs(self) -> list[dict]:
        """合并文件配置和数据库配置

        Returns:
            list[dict]: 合并后的配置列表
        """
        file_servers = await self.load_config()
        db_servers = await self.load_from_database()

        merged = {}
        for server in file_servers:
            merged[server["name"]] = server

        for server in db_servers:
            name = server["name"]
            if name not in merged:
                merged[name] = server

        return list(merged.values())

    def get_config_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_path

    def validate_config(self, server: dict) -> bool:
        """验证 Server 配置

        Args:
            server: Server 配置

        Returns:
            bool: 配置是否有效
        """
        if not server.get("name"):
            logger.error("Server config missing 'name'")
            return False

        transport = server.get("transport")
        if not transport:
            logger.error("Server config missing 'transport'")
            return False

        config = server.get("config", {})
        if transport == MCPTransport.STDIO:
            if not config.get("command"):
                logger.error(f"stdio transport requires 'command' in config for {server['name']}")
                return False
        elif transport in (MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP):
            if not config.get("url"):
                logger.error(f"{transport.value} transport requires 'url' in config for {server['name']}")
                return False

        return True