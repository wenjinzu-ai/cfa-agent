from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite


_TS_DEFAULT = "strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')"

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT})
);

CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_history(session_id, created_at);

CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    session_id TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT}),
    updated_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT})
);

CREATE INDEX IF NOT EXISTS idx_memory_type_category ON memory_entries(type, category);
CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_entries(session_id);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memory_entries(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_entries_fts USING fts5(
    content,
    content=memory_entries,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON memory_entries BEGIN
    INSERT INTO memory_entries_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_fts_update AFTER UPDATE ON memory_entries BEGIN
    DELETE FROM memory_entries_fts WHERE rowid = old.id;
    INSERT INTO memory_entries_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_fts_delete AFTER DELETE ON memory_entries BEGIN
    INSERT INTO memory_entries_fts(memory_entries_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    parent_plan_id TEXT,
    session_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'running',
    steps_json TEXT NOT NULL,
    rollback_point_json TEXT,
    created_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT}),
    updated_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT})
);

CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_parent ON plans(parent_plan_id);
CREATE INDEX IF NOT EXISTS idx_plans_session ON plans(session_id);

CREATE TRIGGER IF NOT EXISTS plans_updated AFTER UPDATE ON plans BEGIN
    UPDATE plans SET updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now') WHERE id = new.id;
END;

CREATE TRIGGER IF NOT EXISTS memory_entries_updated AFTER UPDATE ON memory_entries BEGIN
    UPDATE memory_entries SET updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'), last_accessed_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now') WHERE id = new.id;
END;

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT,
    step_id INTEGER,
    event_type TEXT NOT NULL,
    event_category TEXT NOT NULL,
    content TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT ({_TS_DEFAULT})
);

CREATE INDEX IF NOT EXISTS idx_audit_plan ON audit_log(plan_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type, created_at);
"""


_VALID_TABLES = frozenset({
    "conversation_history",
    "memory_entries",
    "memory_tags",
    "plans",
    "audit_log",
})


class SQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @staticmethod
    def _validate_table(table: str) -> str:
        if table not in _VALID_TABLES:
            raise ValueError(f"Invalid table name: {table}")
        return table

    @staticmethod
    def _quote_identifier(name: str) -> str:
        if not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid identifier: {name}")
        return f'"{name}"'

    @classmethod
    def _validate_order_by(cls, order_by: str) -> str:
        parts = order_by.strip().split()
        if len(parts) < 1 or len(parts) > 2:
            raise ValueError(f"Invalid order_by: {order_by}")
        col = cls._quote_identifier(parts[0])
        direction = parts[1].upper() if len(parts) == 2 else ""
        if direction and direction not in ("ASC", "DESC"):
            raise ValueError(f"Invalid order direction: {direction}")
        return f"{col} {direction}".strip()

    async def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "SQLiteStore":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        return self._conn

    async def execute_sql(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = await self._get_conn()
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def execute_write(self, sql: str, params: tuple = ()) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(sql, params)
        await conn.commit()
        return cursor.lastrowid

    async def insert(self, table: str, data: dict) -> int:
        table = self._validate_table(table)
        columns = ", ".join(self._quote_identifier(k) for k in data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = tuple(data.values())
        return await self.execute_write(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values
        )

    async def insert_many(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        table = self._validate_table(table)
        conn = await self._get_conn()
        columns = ", ".join(self._quote_identifier(k) for k in rows[0].keys())
        placeholders = ", ".join(["?"] * len(rows[0]))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        count = 0
        try:
            for row in rows:
                await conn.execute(sql, tuple(row.values()))
                count += 1
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        return count

    async def find_one(self, table: str, conditions: dict) -> dict | None:
        table = self._validate_table(table)
        where_clause, params = self._build_where(conditions)
        conn = await self._get_conn()
        cursor = await conn.execute(f"SELECT * FROM {table} WHERE {where_clause}", params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def find_all(
        self,
        table: str,
        conditions: dict | None = None,
        order_by: str | None = None,
        limit: int = 0,
    ) -> list[dict]:
        table = self._validate_table(table)
        sql = f"SELECT * FROM {table}"
        params: tuple = ()

        if conditions:
            where_clause, params = self._build_where(conditions)
            sql += f" WHERE {where_clause}"

        if order_by:
            sql += f" ORDER BY {self._validate_order_by(order_by)}"

        if limit > 0:
            sql += f" LIMIT {limit}"

        return await self.execute_sql(sql, params)

    async def update(self, table: str, data: dict, conditions: dict) -> int:
        table = self._validate_table(table)
        set_clause = ", ".join([f"{self._quote_identifier(k)} = ?" for k in data.keys()])
        where_clause, where_params = self._build_where(conditions)
        params = tuple(data.values()) + where_params

        conn = await self._get_conn()
        cursor = await conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where_clause}", params
        )
        await conn.commit()
        return cursor.rowcount

    async def delete(self, table: str, conditions: dict) -> int:
        table = self._validate_table(table)
        where_clause, params = self._build_where(conditions)
        conn = await self._get_conn()
        cursor = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", params)
        await conn.commit()
        return cursor.rowcount

    @staticmethod
    def _build_where(conditions: dict) -> tuple[str, tuple]:
        clauses = []
        params = []
        for key, value in conditions.items():
            quoted_key = SQLiteStore._quote_identifier(key)
            if value is None:
                clauses.append(f"{quoted_key} IS NULL")
            else:
                clauses.append(f"{quoted_key} = ?")
                params.append(value)
        return " AND ".join(clauses), tuple(params)

    async def add_memory_entry(self, entry: dict) -> int:
        entry_copy = dict(entry)
        tags = entry_copy.pop("tags", [])
        entry_id = await self.insert("memory_entries", entry_copy)

        if tags:
            tag_rows = [{"memory_id": entry_id, "tag": tag} for tag in tags]
            await self.insert_many("memory_tags", tag_rows)

        return entry_id

    async def search_memories_fts(self, query: str, limit: int = 20) -> list[dict]:
        sql = """
            SELECT m.*, fts.rank
            FROM memory_entries_fts fts
            JOIN memory_entries m ON m.id = fts.rowid
            WHERE memory_entries_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
        """
        return await self.execute_sql(sql, (query, limit))

    async def search_memories_by_tags(self, tags: list[str], limit: int = 20) -> list[dict]:
        placeholders = ", ".join(["?"] * len(tags))
        sql = f"""
            SELECT m.*, GROUP_CONCAT(mt.tag) AS matched_tags
            FROM memory_entries m
            JOIN memory_tags mt ON mt.memory_id = m.id
            WHERE mt.tag IN ({placeholders})
            GROUP BY m.id
            ORDER BY m.created_at DESC
            LIMIT ?
        """
        return await self.execute_sql(sql, tuple(tags) + (limit,))

    async def search_memories_recent(
        self,
        category: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        conditions: dict[str, Any] = {}
        if category:
            conditions["category"] = category
        if session_id:
            conditions["session_id"] = session_id
        return await self.find_all("memory_entries", conditions, order_by="created_at DESC", limit=limit)

    async def add_conversation_message(self, message: dict) -> int:
        return await self.insert("conversation_history", message)

    async def get_conversation_history(self, session_id: str, limit: int = 50) -> list[dict]:
        return await self.find_all(
            "conversation_history",
            conditions={"session_id": session_id},
            order_by="created_at ASC",
            limit=limit,
        )

    async def create_plan(self, plan_data: dict) -> str:
        plan_id = plan_data.get("id")
        await self.insert("plans", plan_data)
        return plan_id

    async def update_plan_status(
        self, plan_id: str, status: str, steps_json: str | None = None
    ) -> None:
        data: dict[str, Any] = {"status": status}
        if steps_json is not None:
            data["steps_json"] = steps_json
        await self.update("plans", data, conditions={"id": plan_id})

    async def write_audit_log(self, log_data: dict) -> int:
        return await self.insert("audit_log", log_data)

    async def get_audit_logs(
        self,
        plan_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions: dict[str, Any] = {}
        if plan_id:
            conditions["plan_id"] = plan_id
        if event_type:
            conditions["event_type"] = event_type
        return await self.find_all("audit_log", conditions, order_by="created_at DESC", limit=limit)