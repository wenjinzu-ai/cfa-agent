from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    db_file = tmp_path / "test.db"
    return str(db_file)


@pytest.fixture
def sample_user_message() -> dict:
    return {
        "message": "帮我搜索一下 Python 异步编程的最新进展",
        "session_id": "test-session-001",
        "stream": False,
    }


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="这是测试回复")
    llm.chat_stream = AsyncMock()
    llm.chat_with_tools = AsyncMock(return_value={"content": "", "tool_calls": []})
    llm.count_tokens = MagicMock(return_value=100)
    llm.close = AsyncMock()
    return llm