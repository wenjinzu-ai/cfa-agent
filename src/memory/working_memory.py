from __future__ import annotations

import json
from typing import Any

from src.memory.base import BaseMemory
from src.memory.sqlite_store import SQLiteStore
from src.models.memory import MemoryEntry, RetrievalResult


class WorkingMemory(BaseMemory):
    def __init__(self, store: SQLiteStore):
        self._store = store
        self._cache: dict[str, Any] = {}
        self._persist_on_step: bool = True

    async def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    async def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    async def keys(self) -> list[str]:
        return list(self._cache.keys())

    async def clear(self) -> None:
        self._cache.clear()

    async def persist_to_store(self, plan_id: str, step_id: int) -> None:
        snapshot = json.dumps(self._cache)
        await self._store.execute_write(
            "INSERT INTO audit_log (plan_id, step_id, event_type, event_category, content) VALUES (?, ?, ?, ?, ?)",
            (plan_id, step_id, "plan_update", "decision", snapshot),
        )

    async def restore_from_snapshot(self, snapshot_keys: list[str]) -> None:
        keys_to_remove = [k for k in self._cache if k not in snapshot_keys]
        for k in keys_to_remove:
            del self._cache[k]

    async def store(self, entry: MemoryEntry) -> int:
        return await self._store.add_memory_entry(entry.to_db_dict())

    async def retrieve(self, query: str, **kwargs) -> list[RetrievalResult]:
        return []

    async def get_by_id(self, entry_id: int) -> MemoryEntry | None:
        return None

    async def delete(self, entry_id: int) -> bool:
        return False

    async def update(self, entry: MemoryEntry) -> bool:
        return False