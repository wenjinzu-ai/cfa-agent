"""数据库连接测试"""
from __future__ import annotations

import pytest

from src.db.schema import check_database_schema


class TestDatabaseConnection:
    """数据库连接管理测试"""

    @pytest.mark.asyncio
    async def test_connect(self, db_connection):
        """测试数据库连接"""
        assert db_connection._connection is not None

    @pytest.mark.asyncio
    async def test_execute_query(self, db_connection):
        """测试执行查询"""
        cursor = await db_connection.execute("SELECT 1")
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_wal_mode(self, db_connection):
        """测试 WAL 模式"""
        cursor = await db_connection.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].lower() == "wal"

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self, db_connection):
        """测试外键约束"""
        cursor = await db_connection.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
        assert row[0] == 1


class TestDatabaseSchema:
    """数据库 Schema 测试"""

    @pytest.mark.asyncio
    async def test_schema_initialized(self, db_connection):
        """测试 Schema 已初始化"""
        assert await check_database_schema(db_connection)

    @pytest.mark.asyncio
    async def test_agents_table_exists(self, db_connection):
        """测试 agents 表存在"""
        cursor = await db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_tasks_table_exists(self, db_connection):
        """测试 tasks 表存在"""
        cursor = await db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_memories_fts_table_exists(self, db_connection):
        """测试 memories_fts 全文索引表存在"""
        cursor = await db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_all_tables_created(self, db_connection):
        """测试所有核心表已创建"""
        expected_tables = [
            "agents",
            "agent_tool_bindings",
            "tools",
            "tool_executions",
            "mcp_servers",
            "mcp_tools",
            "tasks",
            "sessions",
            "memories",
            "memories_fts",
            "react_steps",
            "events",
            "audit_log",
            "cluster_config",
        ]
        cursor = await db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        rows = await cursor.fetchall()
        table_names = {row[0] for row in rows}
        for table in expected_tables:
            assert table in table_names, f"Table '{table}' not found"