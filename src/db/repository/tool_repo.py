"""CFA-Agent 工具 Repository

封装 tools 表和 tool_executions 表的数据访问操作
"""
from __future__ import annotations

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import ToolStatus


class ToolRepository(BaseRepository):
    """工具 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create(
        self,
        name: str,
        version: str = "1.0.0",
    ) -> dict:
        """注册工具"""
        await self.execute(
            """
            INSERT OR IGNORE INTO tools (name, version, status)
            VALUES (?, ?, ?)
            """,
            (name, version, ToolStatus.ACTIVE.value),
        )
        await self.commit()
        return await self.get_by_name(name)

    async def get_by_name(self, name: str) -> dict | None:
        """根据名称获取工具"""
        return await self.fetch_one("SELECT * FROM tools WHERE name = ?", (name,))

    async def get_active_tools(self) -> list[dict]:
        """获取所有活跃工具"""
        return await self.fetch_all(
            "SELECT * FROM tools WHERE status = ? ORDER BY name",
            (ToolStatus.ACTIVE.value,),
        )

    async def update_status(self, name: str, status: ToolStatus) -> bool:
        """更新工具状态"""
        await self.execute(
            "UPDATE tools SET status = ? WHERE name = ?",
            (status.value, name),
        )
        await self.commit()
        return True

    async def increment_usage(self, name: str) -> bool:
        """增加使用次数"""
        await self.execute(
            "UPDATE tools SET usage_count = usage_count + 1 WHERE name = ?",
            (name,),
        )
        await self.commit()
        return True

    async def update_rating(self, name: str, rating: float) -> bool:
        """更新平均评分"""
        await self.execute(
            "UPDATE tools SET avg_rating = ? WHERE name = ?",
            (rating, name),
        )
        await self.commit()
        return True

    async def delete(self, name: str) -> bool:
        """删除工具"""
        await self.execute("DELETE FROM tools WHERE name = ?", (name,))
        await self.commit()
        return True

    # ---- 工具执行日志 ----

    async def log_execution(
        self,
        tool_name: str,
        status: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        input_params: dict | None = None,
        output_result: dict | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """记录工具执行日志"""
        await self.execute(
            """
            INSERT INTO tool_executions (
                tool_name, agent_id, task_id, input_params, output_result,
                status, duration_ms, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_name,
                agent_id,
                task_id,
                self._json_dumps(input_params),
                self._json_dumps(output_result),
                status,
                duration_ms,
                error_message,
            ),
        )
        await self.commit()

    async def get_execution_history(
        self, tool_name: str, limit: int = 50
    ) -> list[dict]:
        """获取工具执行历史"""
        rows = await self.fetch_all(
            "SELECT * FROM tool_executions WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
            (tool_name, limit),
        )
        for row in rows:
            row["input_params"] = self._json_loads(row.get("input_params"))
            row["output_result"] = self._json_loads(row.get("output_result"))
        return rows

    async def get_agent_executions(
        self, agent_id: str, limit: int = 50
    ) -> list[dict]:
        """获取智能体的工具执行历史"""
        rows = await self.fetch_all(
            "SELECT * FROM tool_executions WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        for row in rows:
            row["input_params"] = self._json_loads(row.get("input_params"))
            row["output_result"] = self._json_loads(row.get("output_result"))
        return rows