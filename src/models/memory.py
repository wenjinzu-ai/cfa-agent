from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from typing import Any


class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    EXPERIENCE = "experience"
    KNOWLEDGE = "knowledge"
    PROFILE = "profile"


class MemoryEntry(BaseModel):
    id: int | None = None
    type: MemoryType
    category: MemoryCategory
    content: str
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    access_count: int = 0
    last_accessed_at: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "category": self.category.value,
            "content": self.content,
            "session_id": self.session_id,
            "tags": self.tags,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any], tags: list[str] | None = None) -> "MemoryEntry":
        return cls(
            id=row.get("id"),
            type=MemoryType(row["type"]),
            category=MemoryCategory(row["category"]),
            content=row["content"],
            session_id=row.get("session_id"),
            tags=tags or [],
            access_count=row.get("access_count", 0),
            last_accessed_at=row.get("last_accessed_at"),
            created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=row.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


class RetrievalResult(BaseModel):
    entry: MemoryEntry
    score: float
    matched_by: list[str] = Field(default_factory=list)