import pytest
from src.memory.long_term import LongTermMemory
from src.models.memory import MemoryEntry, MemoryType, MemoryCategory
from src.common.exceptions import AgentMemoryError


@pytest.fixture
async def long_term(store):
    return LongTermMemory(store)


class TestLongTermMemory:
    @pytest.mark.asyncio
    async def test_store_and_get_by_id(self, long_term):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="FastAPI is a web framework",
            tags=["python", "web"],
        )
        entry_id = await long_term.store(entry)
        assert entry_id > 0

        result = await long_term.get_by_id(entry_id)
        assert result is not None
        assert result.content == "FastAPI is a web framework"
        assert "python" in result.tags

    @pytest.mark.asyncio
    async def test_store_rejects_wrong_type(self, long_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Test",
            session_id="sess-001",
        )
        with pytest.raises(AgentMemoryError):
            await long_term.store(entry)

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, long_term):
        result = await long_term.get_by_id(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, long_term):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="To delete",
        )
        entry_id = await long_term.store(entry)
        assert await long_term.delete(entry_id) is True
        assert await long_term.get_by_id(entry_id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, long_term):
        assert await long_term.delete(9999) is False

    @pytest.mark.asyncio
    async def test_update(self, long_term):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="Original",
        )
        entry_id = await long_term.store(entry)

        entry.id = entry_id
        entry.content = "Updated"
        assert await long_term.update(entry) is True

        updated = await long_term.get_by_id(entry_id)
        assert updated is not None
        assert updated.content == "Updated"

    @pytest.mark.asyncio
    async def test_update_without_id(self, long_term):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="No ID",
        )
        assert await long_term.update(entry) is False

    @pytest.mark.asyncio
    async def test_add_experience(self, long_term):
        entry_id = await long_term.add_experience(
            task_description="Search Python docs",
            outcome="Found useful results",
            tags=["search", "python"],
        )
        assert entry_id > 0
        result = await long_term.get_by_id(entry_id)
        assert result is not None
        assert "Search Python docs" in result.content
        assert "search" in result.tags

    @pytest.mark.asyncio
    async def test_retrieve_combined_search(self, long_term, store):
        await long_term.store(MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="Python async programming with asyncio",
            tags=["python", "async"],
        ))
        await long_term.store(MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="JavaScript promises and async await",
            tags=["javascript", "async"],
        ))
        results = await long_term.retrieve("Python", tags=["python"])
        assert len(results) >= 1
        assert any("Python" in r.entry.content for r in results)