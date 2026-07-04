import pytest
from src.memory.sqlite_store import SQLiteStore


class TestSQLiteStoreInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, store):
        tables = await store.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [t["name"] for t in tables]
        assert "conversation_history" in table_names
        assert "memory_entries" in table_names
        assert "memory_tags" in table_names
        assert "plans" in table_names
        assert "audit_log" in table_names

    @pytest.mark.asyncio
    async def test_initialize_creates_fts(self, store):
        tables = await store.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
        )
        assert len(tables) >= 1

    @pytest.mark.asyncio
    async def test_wal_mode(self, store):
        result = await store.execute_sql("PRAGMA journal_mode")
        assert result[0]["journal_mode"] in ("wal",)

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self, store):
        result = await store.execute_sql("PRAGMA foreign_keys")
        assert result[0]["foreign_keys"] == 1


class TestSQLiteStoreCRUD:
    @pytest.mark.asyncio
    async def test_insert_and_find_one(self, store):
        row_id = await store.insert("conversation_history", {
            "session_id": "sess-001",
            "role": "user",
            "content": "Hello",
        })
        assert row_id > 0
        row = await store.find_one("conversation_history", conditions={"id": row_id})
        assert row is not None
        assert row["content"] == "Hello"
        assert row["session_id"] == "sess-001"

    @pytest.mark.asyncio
    async def test_insert_many(self, store):
        rows = [
            {"session_id": "sess-001", "role": "user", "content": "Hi"},
            {"session_id": "sess-001", "role": "assistant", "content": "Hello!"},
        ]
        count = await store.insert_many("conversation_history", rows)
        assert count == 2

    @pytest.mark.asyncio
    async def test_find_all(self, store):
        await store.insert("conversation_history", {"session_id": "sess-001", "role": "user", "content": "A"})
        await store.insert("conversation_history", {"session_id": "sess-001", "role": "assistant", "content": "B"})
        await store.insert("conversation_history", {"session_id": "sess-002", "role": "user", "content": "C"})
        results = await store.find_all("conversation_history", conditions={"session_id": "sess-001"})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_find_all_with_order_and_limit(self, store):
        for i in range(5):
            await store.insert("conversation_history", {"session_id": "sess-001", "role": "user", "content": f"msg-{i}"})
        results = await store.find_all("conversation_history", conditions={"session_id": "sess-001"}, order_by="id DESC", limit=2)
        assert len(results) == 2
        assert results[0]["content"] == "msg-4"

    @pytest.mark.asyncio
    async def test_update(self, store):
        row_id = await store.insert("conversation_history", {"session_id": "sess-001", "role": "user", "content": "old"})
        affected = await store.update("conversation_history", {"content": "new"}, conditions={"id": row_id})
        assert affected == 1
        row = await store.find_one("conversation_history", conditions={"id": row_id})
        assert row["content"] == "new"

    @pytest.mark.asyncio
    async def test_delete(self, store):
        row_id = await store.insert("conversation_history", {"session_id": "sess-001", "role": "user", "content": "temp"})
        affected = await store.delete("conversation_history", conditions={"id": row_id})
        assert affected == 1
        row = await store.find_one("conversation_history", conditions={"id": row_id})
        assert row is None

    @pytest.mark.asyncio
    async def test_find_one_not_found(self, store):
        row = await store.find_one("conversation_history", conditions={"id": 9999})
        assert row is None

    @pytest.mark.asyncio
    async def test_find_all_no_conditions(self, store):
        await store.insert("conversation_history", {"session_id": "s1", "role": "user", "content": "A"})
        results = await store.find_all("conversation_history")
        assert len(results) >= 1


class TestSQLiteStoreMemory:
    @pytest.mark.asyncio
    async def test_add_memory_entry_with_tags(self, store):
        entry_id = await store.add_memory_entry({
            "type": "long_term",
            "category": "knowledge",
            "content": "Python is a programming language",
            "session_id": None,
            "tags": ["python", "programming"],
        })
        assert entry_id > 0
        row = await store.find_one("memory_entries", conditions={"id": entry_id})
        assert row["content"] == "Python is a programming language"
        tags = await store.find_all("memory_tags", conditions={"memory_id": entry_id})
        tag_values = [t["tag"] for t in tags]
        assert "python" in tag_values
        assert "programming" in tag_values

    @pytest.mark.asyncio
    async def test_add_memory_entry_without_tags(self, store):
        entry_id = await store.add_memory_entry({
            "type": "short_term",
            "category": "experience",
            "content": "User prefers dark mode",
            "session_id": "sess-001",
        })
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_search_memories_fts(self, store):
        await store.add_memory_entry({
            "type": "long_term",
            "category": "knowledge",
            "content": "FastAPI is a modern web framework for Python",
            "session_id": None,
            "tags": [],
        })
        await store.add_memory_entry({
            "type": "long_term",
            "category": "knowledge",
            "content": "Django is a mature web framework",
            "session_id": None,
            "tags": [],
        })
        results = await store.search_memories_fts("FastAPI")
        assert len(results) >= 1
        assert "FastAPI" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_search_memories_by_tags(self, store):
        await store.add_memory_entry({
            "type": "long_term",
            "category": "knowledge",
            "content": "Async programming in Python",
            "session_id": None,
            "tags": ["python", "async"],
        })
        results = await store.search_memories_by_tags(["python"], limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_memories_recent(self, store):
        await store.add_memory_entry({
            "type": "short_term",
            "category": "experience",
            "content": "Recent task result",
            "session_id": "sess-001",
        })
        results = await store.search_memories_recent(session_id="sess-001", limit=10)
        assert len(results) >= 1


class TestSQLiteStoreConversation:
    @pytest.mark.asyncio
    async def test_add_and_get_conversation(self, store):
        await store.add_conversation_message({"session_id": "sess-001", "role": "user", "content": "Hi"})
        await store.add_conversation_message({"session_id": "sess-001", "role": "assistant", "content": "Hello!"})
        history = await store.get_conversation_history("sess-001")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"


class TestSQLiteStorePlans:
    @pytest.mark.asyncio
    async def test_create_plan(self, store):
        plan_id = await store.create_plan({
            "id": "plan-001",
            "session_id": "sess-001",
            "goal": "Search for Python",
            "steps_json": "[]",
            "status": "running",
        })
        assert plan_id == "plan-001"
        row = await store.find_one("plans", conditions={"id": "plan-001"})
        assert row["goal"] == "Search for Python"

    @pytest.mark.asyncio
    async def test_update_plan_status(self, store):
        await store.create_plan({
            "id": "plan-002",
            "session_id": "sess-001",
            "goal": "Test",
            "steps_json": "[]",
            "status": "running",
        })
        await store.update_plan_status("plan-002", "completed")
        row = await store.find_one("plans", conditions={"id": "plan-002"})
        assert row["status"] == "completed"


class TestSQLiteStoreAuditLog:
    @pytest.mark.asyncio
    async def test_write_and_get_audit_logs(self, store):
        await store.write_audit_log({
            "plan_id": "plan-001",
            "step_id": 1,
            "event_type": "thought",
            "event_category": "decision",
            "content": "Analyzing user request",
        })
        logs = await store.get_audit_logs(plan_id="plan-001")
        assert len(logs) >= 1
        assert logs[0]["event_type"] == "thought"

    @pytest.mark.asyncio
    async def test_get_audit_logs_by_event_type(self, store):
        await store.write_audit_log({
            "plan_id": "plan-003",
            "step_id": 1,
            "event_type": "action",
            "event_category": "tool_call",
            "content": "Calling web_search",
        })
        logs = await store.get_audit_logs(event_type="action")
        assert len(logs) >= 1