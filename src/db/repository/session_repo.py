"""CFA-Agent 会话 Repository

封装 sessions 表的数据访问操作
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import SessionStatus


class SessionRepository(BaseRepository):
    """会话 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create(
        self,
        session_id: str,
        expires_at: str | None = None,
    ) -> dict:
        """创建会话"""
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            """
            INSERT INTO sessions (id, status, session_history, last_activity_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                SessionStatus.ACTIVE.value,
                self._json_dumps([]),
                now,
                expires_at,
            ),
        )
        await self.commit()
        return await self.get_by_id(session_id)

    async def get_by_id(self, session_id: str) -> dict | None:
        """根据 ID 获取会话"""
        row = await self.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if row:
            row["session_history"] = self._json_loads(row.get("session_history"))
        return row

    async def update_activity(self, session_id: str) -> bool:
        """更新最后活动时间"""
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "UPDATE sessions SET last_activity_at = ? WHERE id = ?",
            (now, session_id),
        )
        await self.commit()
        return True

    async def append_history(self, session_id: str, message: dict) -> bool:
        """追加对话历史"""
        session = await self.get_by_id(session_id)
        if session is None:
            return False

        history: list = session.get("session_history", [])
        history.append(message)

        if len(history) > 20:
            history = history[-20:]

        await self.execute(
            "UPDATE sessions SET session_history = ? WHERE id = ?",
            (self._json_dumps(history), session_id),
        )
        await self.update_activity(session_id)
        return True

    async def update_summary(self, session_id: str, summary: str) -> bool:
        """更新会话摘要"""
        await self.execute(
            "UPDATE sessions SET summary = ? WHERE id = ?",
            (summary, session_id),
        )
        await self.commit()
        return True

    async def update_status(self, session_id: str, status: SessionStatus) -> bool:
        """更新会话状态"""
        await self.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (status.value, session_id),
        )
        await self.commit()
        return True

    async def archive_expired(self, timeout_minutes: int = 30) -> int:
        """归档超时会话"""
        now = datetime.now(timezone.utc)
        cutoff = now.isoformat()

        await self.execute(
            """
            UPDATE sessions SET status = ?
            WHERE status = ? AND last_activity_at < datetime(?, ?)
            """,
            (
                SessionStatus.ARCHIVED.value,
                SessionStatus.ACTIVE.value,
                cutoff,
                f"-{timeout_minutes} minutes",
            ),
        )
        await self.commit()
        cursor = await self.db.execute("SELECT changes()")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def delete(self, session_id: str) -> bool:
        """删除会话"""
        await self.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.commit()
        return True