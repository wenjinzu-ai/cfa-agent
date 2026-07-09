"""CFA-Agent 事件 Repository

封装 events 表和 audit_log 表的数据访问操作
"""
from __future__ import annotations

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import EventType


class EventRepository(BaseRepository):
    """事件 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create_event(
        self,
        event_type: EventType | str,
        payload: dict | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """创建事件"""
        event_type_value = event_type.value if isinstance(event_type, EventType) else event_type
        await self.execute(
            """
            INSERT INTO events (event_type, agent_id, task_id, payload)
            VALUES (?, ?, ?, ?)
            """,
            (event_type_value, agent_id, task_id, self._json_dumps(payload)),
        )
        await self.commit()

    async def get_events_by_type(
        self, event_type: EventType | str, limit: int = 50
    ) -> list[dict]:
        """按类型获取事件"""
        event_type_value = event_type.value if isinstance(event_type, EventType) else event_type
        rows = await self.fetch_all(
            "SELECT * FROM events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type_value, limit),
        )
        for row in rows:
            row["payload"] = self._json_loads(row.get("payload"))
        return rows

    async def get_events_by_agent(
        self, agent_id: str, limit: int = 50
    ) -> list[dict]:
        """按智能体获取事件"""
        rows = await self.fetch_all(
            "SELECT * FROM events WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        for row in rows:
            row["payload"] = self._json_loads(row.get("payload"))
        return rows

    async def get_events_by_task(
        self, task_id: str, limit: int = 50
    ) -> list[dict]:
        """按任务获取事件"""
        rows = await self.fetch_all(
            "SELECT * FROM events WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
            (task_id, limit),
        )
        for row in rows:
            row["payload"] = self._json_loads(row.get("payload"))
        return rows

    async def get_pending_events(
        self, agent_id: str, event_type: EventType | str | None = None
    ) -> list[dict]:
        """获取待处理事件（用于跨进程轮询）"""
        event_type_value = (
            event_type.value if isinstance(event_type, EventType) else event_type
        )
        if event_type_value:
            rows = await self.fetch_all(
                "SELECT * FROM events WHERE agent_id = ? AND event_type = ? ORDER BY created_at",
                (agent_id, event_type_value),
            )
        else:
            rows = await self.fetch_all(
                "SELECT * FROM events WHERE agent_id = ? ORDER BY created_at",
                (agent_id,),
            )
        for row in rows:
            row["payload"] = self._json_loads(row.get("payload"))
        return rows

    async def delete_event(self, event_id: int) -> bool:
        """删除事件"""
        await self.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await self.commit()
        return True

    # ---- 审计日志 ----

    async def create_audit_log(
        self,
        action: str,
        agent_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """创建审计日志"""
        await self.execute(
            """
            INSERT INTO audit_log (agent_id, action, details, ip_address)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, action, self._json_dumps(details), ip_address),
        )
        await self.commit()

    async def get_audit_logs(
        self, agent_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        """获取审计日志"""
        if agent_id:
            rows = await self.fetch_all(
                "SELECT * FROM audit_log WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit),
            )
        else:
            rows = await self.fetch_all(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        for row in rows:
            row["details"] = self._json_loads(row.get("details"))
        return rows