from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.memory import MemoryEntry, RetrievalResult


class BaseMemory(ABC):
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> int:
        ...

    @abstractmethod
    async def retrieve(self, query: str, **kwargs) -> list[RetrievalResult]:
        ...

    @abstractmethod
    async def get_by_id(self, entry_id: int) -> MemoryEntry | None:
        ...

    @abstractmethod
    async def delete(self, entry_id: int) -> bool:
        ...

    @abstractmethod
    async def update(self, entry: MemoryEntry) -> bool:
        ...