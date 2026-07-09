"""CFA-Agent 数据库连接管理

基于 aiosqlite 实现异步 SQLite 连接管理，支持 WAL 模式和连接池
"""
from __future__ import annotations

import aiosqlite
from pathlib import Path

from src.common.settings import get_config
from src.common.exceptions import DatabaseError


class DatabaseConnection:
    """数据库连接管理器

    职责：
    - 管理 aiosqlite 异步连接
    - 启用 WAL 模式提升并发读写性能
    - 启用外键约束
    - 管理连接生命周期
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or get_config().database.db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        """建立数据库连接"""
        if self._connection is not None:
            return self._connection

        db_path = Path(self._db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._connection = await aiosqlite.connect(str(db_path))
            self._connection.row_factory = aiosqlite.Row

            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA foreign_keys=ON")
            await self._connection.execute("PRAGMA busy_timeout=5000")
            await self._connection.execute("PRAGMA synchronous=NORMAL")

            return self._connection
        except Exception as e:
            raise DatabaseError(f"Failed to connect to database: {e}") from e

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception as e:
                raise DatabaseError(f"Failed to close database connection: {e}") from e
            finally:
                self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        """获取当前连接"""
        if self._connection is None:
            raise DatabaseError("Database connection not established. Call connect() first.")
        return self._connection

    async def execute(self, query: str, parameters: tuple | None = None) -> aiosqlite.Cursor:
        """执行 SQL 语句"""
        conn = self.connection
        try:
            if parameters:
                return await conn.execute(query, parameters)
            return await conn.execute(query)
        except Exception as e:
            raise DatabaseError(f"Failed to execute query: {e}") from e

    async def executescript(self, script: str) -> None:
        """执行 SQL 脚本（用于 Schema 初始化）"""
        conn = self.connection
        try:
            await conn.executescript(script)
        except Exception as e:
            raise DatabaseError(f"Failed to execute script: {e}") from e

    async def commit(self) -> None:
        """提交事务"""
        conn = self.connection
        try:
            await conn.commit()
        except Exception as e:
            raise DatabaseError(f"Failed to commit transaction: {e}") from e


_db_connection: DatabaseConnection | None = None


async def get_db() -> DatabaseConnection:
    """获取全局数据库连接实例（单例模式）"""
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection()
        await _db_connection.connect()
    return _db_connection


async def close_db() -> None:
    """关闭全局数据库连接"""
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None