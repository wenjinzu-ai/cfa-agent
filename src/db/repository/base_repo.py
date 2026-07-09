"""CFA-Agent 基础 Repository

提供通用的 CRUD 操作封装，所有具体 Repository 继承此类
"""
from __future__ import annotations

import json
from typing import Any, TypeVar

from src.db.connection import DatabaseConnection

T = TypeVar("T")


class BaseRepository:
    """基础 Repository 类

    提供通用的数据库操作方法，子类可覆写或扩展
    """

    def __init__(self, db: DatabaseConnection):
        self._db = db

    @property
    def db(self) -> DatabaseConnection:
        return self._db

    @staticmethod
    def _json_dumps(obj: Any) -> str | None:
        """将对象序列化为 JSON 字符串"""
        if obj is None:
            return None
        return json.dumps(obj, ensure_ascii=False, default=str)

    @staticmethod
    def _json_loads(s: str | None) -> Any:
        """将 JSON 字符串反序列化为对象"""
        if s is None:
            return None
        return json.loads(s)

    async def fetch_one(self, query: str, parameters: tuple | None = None) -> dict | None:
        """查询单条记录"""
        cursor = await self.db.execute(query, parameters)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, query: str, parameters: tuple | None = None) -> list[dict]:
        """查询多条记录"""
        cursor = await self.db.execute(query, parameters)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_val(self, query: str, parameters: tuple | None = None) -> Any:
        """查询单个值"""
        cursor = await self.db.execute(query, parameters)
        row = await cursor.fetchone()
        if row is None:
            return None
        return row[0]

    async def execute(self, query: str, parameters: tuple | None = None) -> None:
        """执行写操作"""
        await self.db.execute(query, parameters)

    async def commit(self) -> None:
        """提交事务"""
        await self.db.commit()