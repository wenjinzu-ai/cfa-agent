"""CFA-Agent 记忆 Repository

封装 memories 表和 react_steps 表的数据访问操作
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import MemoryType


class MemoryRepository(BaseRepository):
    """记忆 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create(
        self,
        content: str,
        memory_type: MemoryType,
        agent_id: str | None = None,
        importance: float = 0.5,
        embedding: bytes | None = None,
    ) -> dict:
        """创建记忆"""
        cursor = await self.db.execute(
            """
            INSERT INTO memories (agent_id, memory_type, content, embedding, importance)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, memory_type.value, content, embedding, importance),
        )
        await self.commit()
        memory_id = cursor.lastrowid
        return await self.get_by_id(memory_id)

    async def get_by_id(self, memory_id: int) -> dict | None:
        """根据 ID 获取记忆"""
        return await self.fetch_one("SELECT * FROM memories WHERE id = ?", (memory_id,))

    async def search_fts(self, query: str, limit: int = 10) -> list[dict]:
        """FTS5 全文搜索"""
        rows = await self.fetch_all(
            """
            SELECT m.* FROM memories m
            JOIN memories_fts fts ON m.id = fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        return rows

    async def search_by_type(
        self, memory_type: MemoryType, agent_id: str | None = None, limit: int = 20
    ) -> list[dict]:
        """按类型搜索记忆"""
        if agent_id:
            return await self.fetch_all(
                "SELECT * FROM memories WHERE memory_type = ? AND agent_id = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
                (memory_type.value, agent_id, limit),
            )
        return await self.fetch_all(
            "SELECT * FROM memories WHERE memory_type = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
            (memory_type.value, limit),
        )

    async def update_access(self, memory_id: int) -> bool:
        """更新访问次数和最后访问时间"""
        now = datetime.now(timezone.utc).isoformat()
        await self.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
            (now, memory_id),
        )
        await self.commit()
        return True

    async def update_importance(self, memory_id: int, importance: float) -> bool:
        """更新重要性"""
        await self.execute(
            "UPDATE memories SET importance = ? WHERE id = ?",
            (importance, memory_id),
        )
        await self.commit()
        return True

    async def delete(self, memory_id: int) -> bool:
        """删除记忆"""
        await self.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await self.commit()
        return True

    async def delete_old_memories(self, days: int = 90, min_importance: float = 0.3) -> int:
        """清理旧记忆（重要性低于阈值的超过指定天数的记忆）"""
        await self.execute(
            """
            DELETE FROM memories
            WHERE importance < ? AND created_at < datetime('now', ?)
            """,
            (min_importance, f"-{days} days"),
        )
        await self.commit()
        cursor = await self.db.execute("SELECT changes()")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ---- ReAct 步骤轨迹 ----

    async def create_react_step(
        self,
        task_id: str,
        step_index: int,
        status: str,
        agent_id: str | None = None,
        thought: str | None = None,
        action: dict | None = None,
        observation: str | None = None,
        duration_ms: int | None = None,
    ) -> dict:
        """创建 ReAct 步骤记录"""
        cursor = await self.db.execute(
            """
            INSERT INTO react_steps (
                task_id, agent_id, step_index, thought, action, observation, duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                agent_id,
                step_index,
                thought,
                self._json_dumps(action),
                observation,
                duration_ms,
                status,
            ),
        )
        await self.commit()
        step_id = cursor.lastrowid
        return await self.fetch_one("SELECT * FROM react_steps WHERE id = ?", (step_id,))

    async def get_task_steps(self, task_id: str) -> list[dict]:
        """获取任务的所有 ReAct 步骤"""
        rows = await self.fetch_all(
            "SELECT * FROM react_steps WHERE task_id = ? ORDER BY step_index",
            (task_id,),
        )
        for row in rows:
            row["action"] = self._json_loads(row.get("action"))
        return rows