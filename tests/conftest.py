"""CFA-Agent 测试配置"""
from __future__ import annotations

import pytest
import tempfile

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_connection():
    """创建临时数据库连接用于测试"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from src.db.connection import DatabaseConnection
    from src.db.schema import init_database

    db = DatabaseConnection(db_path)
    await db.connect()
    await init_database(db)

    yield db

    await db.close()

    import os
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
async def agent_repo(db_connection):
    """创建 AgentRepository 实例"""
    from src.db.repository.agent_repo import AgentRepository
    return AgentRepository(db_connection)


@pytest.fixture
async def task_repo(db_connection):
    """创建 TaskRepository 实例"""
    from src.db.repository.task_repo import TaskRepository
    return TaskRepository(db_connection)


@pytest.fixture
async def tool_repo(db_connection):
    """创建 ToolRepository 实例"""
    from src.db.repository.tool_repo import ToolRepository
    return ToolRepository(db_connection)


@pytest.fixture
async def session_repo(db_connection):
    """创建 SessionRepository 实例"""
    from src.db.repository.session_repo import SessionRepository
    return SessionRepository(db_connection)


@pytest.fixture
async def memory_repo(db_connection):
    """创建 MemoryRepository 实例"""
    from src.db.repository.memory_repo import MemoryRepository
    return MemoryRepository(db_connection)


@pytest.fixture
async def event_repo(db_connection):
    """创建 EventRepository 实例"""
    from src.db.repository.event_repo import EventRepository
    return EventRepository(db_connection)