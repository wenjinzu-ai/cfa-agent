import pytest
from src.memory.working_memory import WorkingMemory
from src.models.memory import MemoryEntry, MemoryType, MemoryCategory


@pytest.fixture
async def working_memory(store):
    return WorkingMemory(store)


class TestWorkingMemory:
    @pytest.mark.asyncio
    async def test_set_and_get(self, working_memory):
        await working_memory.set("current_task", "search")
        value = await working_memory.get("current_task")
        assert value == "search"

    @pytest.mark.asyncio
    async def test_get_default(self, working_memory):
        value = await working_memory.get("nonexistent", "default_val")
        assert value == "default_val"

    @pytest.mark.asyncio
    async def test_keys(self, working_memory):
        await working_memory.set("key1", "val1")
        await working_memory.set("key2", "val2")
        keys = await working_memory.keys()
        assert "key1" in keys
        assert "key2" in keys

    @pytest.mark.asyncio
    async def test_clear(self, working_memory):
        await working_memory.set("key1", "val1")
        await working_memory.clear()
        keys = await working_memory.keys()
        assert len(keys) == 0

    @pytest.mark.asyncio
    async def test_restore_from_snapshot(self, working_memory):
        await working_memory.set("keep_key", "keep_val")
        await working_memory.set("remove_key", "remove_val")
        await working_memory.restore_from_snapshot(["keep_key"])
        assert await working_memory.get("keep_key") == "keep_val"
        assert await working_memory.get("remove_key") is None

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty(self, working_memory):
        results = await working_memory.retrieve("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none(self, working_memory):
        result = await working_memory.get_by_id(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_returns_false(self, working_memory):
        result = await working_memory.delete(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_update_returns_false(self, working_memory):
        entry = MemoryEntry(type=MemoryType.SHORT_TERM, category=MemoryCategory.EXPERIENCE, content="test")
        result = await working_memory.update(entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_persist_to_store(self, working_memory, store):
        await working_memory.set("task", "search")
        await working_memory.persist_to_store("plan-001", 1)
        logs = await store.get_audit_logs(plan_id="plan-001")
        assert len(logs) >= 1