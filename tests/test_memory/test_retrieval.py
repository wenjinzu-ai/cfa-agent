import pytest
from src.memory.retrieval import MemoryRetriever


@pytest.fixture
async def retriever(store):
    return MemoryRetriever(store)


@pytest.fixture
async def seeded_store(store):
    await store.add_memory_entry({
        "type": "long_term",
        "category": "knowledge",
        "content": "Python async programming with asyncio and await",
        "session_id": None,
        "tags": ["python", "async"],
    })
    await store.add_memory_entry({
        "type": "long_term",
        "category": "knowledge",
        "content": "FastAPI framework for building APIs in Python",
        "session_id": None,
        "tags": ["python", "web"],
    })
    await store.add_memory_entry({
        "type": "long_term",
        "category": "experience",
        "content": "Web search failed due to network timeout",
        "session_id": None,
        "tags": ["search", "error"],
    })
    return store


class TestMemoryRetriever:
    @pytest.mark.asyncio
    async def test_keyword_search(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.keyword_search("Python")
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_temporal_search(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.temporal_search(limit=10)
        assert len(results) >= 3

    @pytest.mark.asyncio
    async def test_tag_search(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.tag_search(["python"], limit=10)
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_combined_search(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.combined_search("Python", tags=["python"], limit=10)
        assert len(results) >= 1
        assert all(r.score > 0 for r in results)

    @pytest.mark.asyncio
    async def test_combined_search_without_tags(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.combined_search("Python", limit=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_combined_search_results_sorted_by_score(self, seeded_store):
        retriever = MemoryRetriever(seeded_store)
        results = await retriever.combined_search("Python", tags=["python"], limit=10)
        if len(results) >= 2:
            assert results[0].score >= results[1].score

    @pytest.mark.asyncio
    async def test_normalize_fts_rank(self):
        assert MemoryRetriever._normalize_fts_rank(0) == 1.0
        assert MemoryRetriever._normalize_fts_rank(999) < 1.0

    @pytest.mark.asyncio
    async def test_temporal_decay(self):
        assert MemoryRetriever._temporal_decay(0) == 1.0
        assert MemoryRetriever._temporal_decay(100) < 1.0
        assert MemoryRetriever._temporal_decay(100) > 0

    @pytest.mark.asyncio
    async def test_keyword_search_no_results(self, store):
        retriever = MemoryRetriever(store)
        results = await retriever.keyword_search("nonexistent_xyz")
        assert len(results) == 0