from src.models.memory import MemoryEntry, MemoryType, MemoryCategory, RetrievalResult


class TestMemoryType:
    def test_memory_type_values(self):
        assert MemoryType.SHORT_TERM == "short_term"
        assert MemoryType.LONG_TERM == "long_term"


class TestMemoryCategory:
    def test_memory_category_values(self):
        assert MemoryCategory.PREFERENCE == "preference"
        assert MemoryCategory.EXPERIENCE == "experience"
        assert MemoryCategory.KNOWLEDGE == "knowledge"
        assert MemoryCategory.PROFILE == "profile"


class TestMemoryEntry:
    def test_create_entry(self):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="User prefers Python",
        )
        assert entry.type == MemoryType.SHORT_TERM
        assert entry.category == MemoryCategory.EXPERIENCE
        assert entry.content == "User prefers Python"
        assert entry.id is None
        assert entry.session_id is None
        assert entry.tags == []
        assert entry.access_count == 0
        assert entry.last_accessed_at is None
        assert entry.created_at is not None
        assert entry.updated_at is not None

    def test_entry_with_full_data(self):
        entry = MemoryEntry(
            id=1,
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="FastAPI is a web framework",
            session_id="sess-001",
            tags=["python", "web"],
            access_count=5,
            last_accessed_at="2024-01-01T00:00:00Z",
        )
        assert entry.id == 1
        assert entry.session_id == "sess-001"
        assert entry.tags == ["python", "web"]
        assert entry.access_count == 5

    def test_entry_to_db_dict(self):
        entry = MemoryEntry(
            id=1,
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.EXPERIENCE,
            content="Test content",
            session_id="sess-001",
            tags=["tag1", "tag2"],
        )
        db_dict = entry.to_db_dict()
        assert db_dict["type"] == "short_term"
        assert db_dict["category"] == "experience"
        assert db_dict["content"] == "Test content"
        assert db_dict["session_id"] == "sess-001"
        assert db_dict["tags"] == ["tag1", "tag2"]
        assert "id" not in db_dict

    def test_entry_from_db_row(self):
        row = {
            "id": 1,
            "type": "long_term",
            "category": "knowledge",
            "content": "FastAPI is a web framework",
            "session_id": "sess-001",
            "access_count": 5,
            "last_accessed_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        entry = MemoryEntry.from_db_row(row, tags=["python", "web"])
        assert entry.id == 1
        assert entry.type == MemoryType.LONG_TERM
        assert entry.category == MemoryCategory.KNOWLEDGE
        assert entry.tags == ["python", "web"]
        assert entry.access_count == 5

    def test_entry_from_db_row_without_tags(self):
        row = {
            "id": 2,
            "type": "short_term",
            "category": "preference",
            "content": "Test",
            "session_id": None,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        entry = MemoryEntry.from_db_row(row)
        assert entry.tags == []

    def test_entry_roundtrip(self):
        entry = MemoryEntry(
            id=1,
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="Test content",
            session_id="sess-001",
            tags=["tag1"],
            access_count=3,
        )
        db_dict = entry.to_db_dict()
        restored = MemoryEntry.from_db_row(
            {"id": 1, **db_dict},
            tags=["tag1"],
        )
        assert restored.type == entry.type
        assert restored.category == entry.category
        assert restored.content == entry.content
        assert restored.session_id == entry.session_id
        assert restored.tags == entry.tags
        assert restored.access_count == entry.access_count


class TestRetrievalResult:
    def test_create_retrieval_result(self):
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.KNOWLEDGE,
            content="Test content",
        )
        result = RetrievalResult(entry=entry, score=0.95)
        assert result.entry == entry
        assert result.score == 0.95

    def test_retrieval_result_score_range(self):
        entry = MemoryEntry(
            type=MemoryType.SHORT_TERM,
            category=MemoryCategory.PREFERENCE,
            content="Test",
        )
        result = RetrievalResult(entry=entry, score=1.0)
        assert result.score == 1.0