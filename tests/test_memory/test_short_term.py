import pytest
from src.memory.short_term import ShortTermMemory
from src.models.memory import MemoryEntry, MemoryType, MemoryCategory
from src.common.exceptions import AgentMemoryError


@pytest.fixture
async def short_term(store):
    return ShortTermMemory(store)


class TestShortTermMemory:
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="User prefers Python",
            session_id="sess-001",
            tags=["python"],
        )
        entry_id = await short_term.store(entry)
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_store_rejects_wrong_type(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="Test",
            session_id="sess-001",
        )
        with pytest.raises(AgentMemoryError):
            await short_term.store(entry)

    @pytest.mark.asyncio
    async def test_store_requires_session_id(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Test",
        )
        with pytest.raises(AgentMemoryError):
            await short_term.store(entry)

    @pytest.mark.asyncio
    async def test_get_by_id(self, short_term, store):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Test content",
            session_id="sess-001",
            tags=["tag1"],
        )
        entry_id = await short_term.store(entry)
        result = await short_term.get_by_id(entry_id)
        assert result is not None
        assert result.content == "Test content"
        assert "tag1" in result.tags

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, short_term):
        result = await short_term.get_by_id(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="To delete",
            session_id="sess-001",
        )
        entry_id = await short_term.store(entry)
        assert await short_term.delete(entry_id) is True
        assert await short_term.get_by_id(entry_id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, short_term):
        assert await short_term.delete(9999) is False

    @pytest.mark.asyncio
    async def test_update(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Original",
            session_id="sess-001",
        )
        entry_id = await short_term.store(entry)

        entry.id = entry_id
        entry.content = "Updated"
        assert await short_term.update(entry) is True

        updated = await short_term.get_by_id(entry_id)
        assert updated is not None
        assert updated.content == "Updated"

    @pytest.mark.asyncio
    async def test_update_without_id(self, short_term):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="No ID",
            session_id="sess-001",
        )
        assert await short_term.update(entry) is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, short_term):
        entry1 = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Active session",
            session_id="sess-active",
        )
        entry2 = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Expired session",
            session_id="sess-expired",
        )
        await short_term.store(entry1)
        await short_term.store(entry2)

        removed = await short_term.cleanup_expired_sessions({"sess-active"})
        assert removed == 1

    @pytest.mark.asyncio
    async def test_retrieve_fts(self, short_term, store):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Python async programming guide",
            session_id="sess-001",
        )
        await short_term.store(entry)
        results = await short_term.retrieve("Python", session_id="sess-001")
        assert len(results) >= 1