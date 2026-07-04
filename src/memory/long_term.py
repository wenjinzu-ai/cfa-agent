from __future__ import annotations

from src.memory.base import BaseMemory
from src.memory.sqlite_store import SQLiteStore
from src.memory.retrieval import MemoryRetriever
from src.models.memory import MemoryType, MemoryCategory, MemoryEntry, RetrievalResult
from src.common.exceptions import AgentMemoryError


class LongTermMemory(BaseMemory):
    def __init__(self, store: SQLiteStore):
        self._store = store
        self._retriever = MemoryRetriever(store)

    async def store(self, entry: MemoryEntry) -> int:
        if entry.type != MemoryType.LONG_TERM:
            raise AgentMemoryError("LongTermMemory only accepts LONG_TERM entries")
        return await self._store.add_memory_entry(entry.to_db_dict())

    async def retrieve(self, query: str, **kwargs) -> list[RetrievalResult]:
        return await self._retriever.combined_search(query, **kwargs)

    async def add_experience(self, task_description: str, outcome: str, tags: list[str] | None = None) -> int:
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.EXPERIENCE,
            content=f"任务: {task_description}\n结果: {outcome}",
            tags=tags or [],
        )
        return await self._store.add_memory_entry(entry.to_db_dict())

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