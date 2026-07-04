from __future__ import annotations

from src.memory.base import BaseMemory
from src.memory.sqlite_store import SQLiteStore
from src.models.memory import MemoryType, MemoryEntry, RetrievalResult
from src.common.exceptions import AgentMemoryError


class ShortTermMemory(BaseMemory):
    def __init__(self, store: SQLiteStore):
        self._store = store

    async def store(self, entry: MemoryEntry) -> int:
        if entry.type != MemoryType.SHORT_TERM:
            raise AgentMemoryError("ShortTermMemory only accepts SHORT_TERM entries")
        if not entry.session_id:
            raise AgentMemoryError("Short-term memory requires session_id")
        return await self._store.add_memory_entry(entry.to_db_dict())

    async def retrieve(self, query: str, session_id: str | None = None, **kwargs) -> list[RetrievalResult]:
        results = await self._store.search_memories_fts(query, limit=20)
        if session_id:
            results = [r for r in results if r.get("session_id") == session_id]

        memory_ids = [r["id"] for r in results]
        tags_by_id = await self._batch_load_tags(memory_ids)

        return [
            RetrievalResult(
                entry=MemoryEntry.from_db_row(r, tags=tags_by_id.get(r["id"], [])),
                score=1.0,
                matched_by=["keyword"],
            )
            for r in results
        ]

    async def _batch_load_tags(self, memory_ids: list[int]) -> dict[int, list[str]]:
        if not memory_ids:
            return {}
        result: dict[int, list[str]] = {mid: [] for mid in memory_ids}
        placeholders = ", ".join(["?"] * len(memory_ids))
        rows = await self._store.execute_sql(
            f"SELECT memory_id, tag FROM memory_tags WHERE memory_id IN ({placeholders})",
            tuple(memory_ids),
        )
        for row in rows:
            result[row["memory_id"]].append(row["tag"])
        return result

    async def cleanup_expired_sessions(self, active_session_ids: set[str]) -> int:
        all_entries = await self._store.find_all(
            "memory_entries",
            conditions={"type": "short_term"},
        )
        expired = [
            e for e in all_entries
            if e.get("session_id") and e["session_id"] not in active_session_ids
        ]
        for e in expired:
            await self._store.delete("memory_entries", conditions={"id": e["id"]})
        return len(expired)

    async def get_by_id(self, entry_id: int) -> MemoryEntry | None:
        row = await self._store.find_one("memory_entries", conditions={"id": entry_id})
        if row:
            tags_rows = await self._store.find_all("memory_tags", conditions={"memory_id": entry_id})
            tags = [t["tag"] for t in tags_rows]
            return MemoryEntry.from_db_row(row, tags=tags)
        return None

    async def delete(self, entry_id: int) -> bool:
        affected = await self._store.delete("memory_entries", conditions={"id": entry_id})
        return affected > 0

    async def update(self, entry: MemoryEntry) -> bool:
        if entry.id is None:
            return False
        data = entry.to_db_dict()
        tags = data.pop("tags", [])
        affected = await self._store.update("memory_entries", data, conditions={"id": entry.id})
        await self._store.delete("memory_tags", conditions={"memory_id": entry.id})
        if tags:
            tag_rows = [{"memory_id": entry.id, "tag": tag} for tag in tags]
            await self._store.insert_many("memory_tags", tag_rows)
        return affected > 0 or bool(tags)