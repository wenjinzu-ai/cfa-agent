"""CFA-Agent 智能体 Repository

封装 agents 表和 agent_tool_bindings 表的数据访问操作
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import AgentStatus, ToolSource


class AgentRepository(BaseRepository):
    """智能体 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create(
        self,
        agent_id: str,
        name: str,
        role: str = "",
        config: dict | None = None,
    ) -> dict:
        """创建智能体

        Args:
            agent_id: Agent ID（如 supervisor, planner 等）
            name: Agent 名称
            role: 保留字段，填写 agent_id
            config: Agent 配置
        """
        role_value = role or agent_id
        await self.execute(
            """
            INSERT INTO agents (id, name, role, status, config, performance_metrics)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                name,
                role_value,
                AgentStatus.IDLE.value,
                self._json_dumps(config),
                self._json_dumps({"success_rate": 0.0, "avg_duration_ms": 0}),
            ),
        )
        await self.commit()
        return await self.get_by_id(agent_id)

    async def get_by_id(self, agent_id: str) -> dict | None:
        """根据 ID 获取智能体"""
        row = await self.fetch_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
        if row:
            row["config"] = self._json_loads(row.get("config"))
            row["performance_metrics"] = self._json_loads(row.get("performance_metrics"))
        return row

    async def get_by_role(self, role: str) -> list[dict]:
        """根据角色/ID 获取智能体列表"""
        rows = await self.fetch_all(
            "SELECT * FROM agents WHERE role = ? ORDER BY created_at",
            (role,),
        )
        for row in rows:
            row["config"] = self._json_loads(row.get("config"))
            row["performance_metrics"] = self._json_loads(row.get("performance_metrics"))
        return rows

    async def get_by_status(self, status: AgentStatus) -> list[dict]:
        """根据状态获取智能体列表"""
        rows = await self.fetch_all(
            "SELECT * FROM agents WHERE status = ? ORDER BY created_at",
            (status.value,),
        )
        for row in rows:
            row["config"] = self._json_loads(row.get("config"))
            row["performance_metrics"] = self._json_loads(row.get("performance_metrics"))
        return rows

    async def list_all(self) -> list[dict]:
        """获取所有智能体"""
        rows = await self.fetch_all("SELECT * FROM agents ORDER BY created_at")
        for row in rows:
            row["config"] = self._json_loads(row.get("config"))
            row["performance_metrics"] = self._json_loads(row.get("performance_metrics"))
        return rows

    async def update_status(self, agent_id: str, status: AgentStatus) -> bool:
        """更新智能体状态"""
        await self.execute(
            "UPDATE agents SET status = ? WHERE id = ?",
            (status.value, agent_id),
        )
        await self.commit()
        return True

    async def update_heartbeat(self, agent_id: str) -> bool:
        """更新心跳时间"""
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "UPDATE agents SET last_heartbeat = ? WHERE id = ?",
            (now, agent_id),
        )
        await self.commit()
        return True

    async def update_config(self, agent_id: str, config: dict) -> bool:
        """更新智能体配置"""
        await self.execute(
            "UPDATE agents SET config = ? WHERE id = ?",
            (self._json_dumps(config), agent_id),
        )
        await self.commit()
        return True

    async def update_performance_metrics(self, agent_id: str, metrics: dict) -> bool:
        """更新性能指标"""
        await self.execute(
            "UPDATE agents SET performance_metrics = ? WHERE id = ?",
            (self._json_dumps(metrics), agent_id),
        )
        await self.commit()
        return True

    async def delete(self, agent_id: str) -> bool:
        """删除智能体"""
        await self.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await self.commit()
        return True

    # ---- 工具绑定 ----

    async def bind_tool(
        self,
        agent_id: str,
        tool_name: str,
        tool_source: ToolSource = ToolSource.BUILTIN,
        proficiency: float = 0.5,
    ) -> bool:
        """绑定工具到智能体"""
        await self.execute(
            """
            INSERT OR REPLACE INTO agent_tool_bindings (agent_id, tool_name, tool_source, proficiency)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, tool_name, tool_source.value, proficiency),
        )
        await self.commit()
        return True

    async def unbind_tool(self, agent_id: str, tool_name: str) -> bool:
        """解绑工具"""
        await self.execute(
            "DELETE FROM agent_tool_bindings WHERE agent_id = ? AND tool_name = ?",
            (agent_id, tool_name),
        )
        await self.commit()
        return True

    async def get_agent_tools(self, agent_id: str) -> list[dict]:
        """获取智能体绑定的所有工具"""
        return await self.fetch_all(
            "SELECT * FROM agent_tool_bindings WHERE agent_id = ?",
            (agent_id,),
        )

    async def get_idle_agent_by_role(self, role: str) -> dict | None:
        """获取指定角色/ID的空闲智能体"""
        row = await self.fetch_one(
            "SELECT * FROM agents WHERE role = ? AND status = ? ORDER BY last_heartbeat DESC LIMIT 1",
            (role, AgentStatus.IDLE.value),
        )
        if row:
            row["config"] = self._json_loads(row.get("config"))
            row["performance_metrics"] = self._json_loads(row.get("performance_metrics"))
        return row