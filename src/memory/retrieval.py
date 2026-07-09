"""CFA-Agent 记忆检索策略

FTS5 全文搜索 + 融合排序，实现混合检索

技术方案 §7.9：
- FTS5 关键词检索（精确匹配）
- 按重要性和时间衰减加权排序
- 结果去重和融合
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.common.types import MemoryType
from src.db.repository.memory_repo import MemoryRepository

logger = logging.getLogger("cfa-agent.memory.retrieval")


class MemoryRetrieval:
    """记忆检索策略

    职责：
    - FTS5 全文搜索
    - 混合检索（FTS5 + 重要性加权）
    - 结果排序和过滤

    Attributes:
        _repo: 记忆数据访问层
    """

    def __init__(self, memory_repo: MemoryRepository):
        self._repo = memory_repo

    async def search_fts(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """FTS5 全文搜索

        Args:
            query: 搜索关键词
            memory_type: 记忆类型过滤
            limit: 返回数量上限

        Returns:
            list[dict]: 匹配的记忆列表
        """
        results = await self._repo.search_fts(query, limit * 2)

        if memory_type:
            results = [r for r in results if r["memory_type"] == memory_type.value]

        return results[:limit]

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[dict]:
        """混合检索

        融合 FTS5 关键词匹配和重要性排序

        Args:
            query: 搜索关键词
            limit: 返回数量上限
            memory_type: 记忆类型过滤

        Returns:
            list[dict]: 排序后的记忆列表
        """
        fts_results = await self.search_fts(query, memory_type, limit * 3)

        type_results = []
        if memory_type:
            type_results = await self._repo.search_by_type(memory_type, limit=limit * 2)

        all_results = {r["id"]: r for r in type_results}
        for r in fts_results:
            if r["id"] not in all_results:
                all_results[r["id"]] = r

        scored = []
        now = datetime.now(timezone.utc)
        for mem in all_results.values():
            score = self._score_memory(mem, query, now)
            scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [mem for mem, _ in scored[:limit]]

    def _score_memory(self, memory: dict, query: str, now: datetime) -> float:
        """计算记忆的相关性得分

        综合因素：
        - 重要性 (importance) * 0.4
        - 访问热度 (access_count) * 0.2
        - 时间衰减 (越新越高) * 0.2
        - 关键词匹配度 * 0.2

        Args:
            memory: 记忆记录
            query: 查询关键词
            now: 当前时间

        Returns:
            float: 综合得分
        """
        importance = memory.get("importance", 0.5)
        access_count = min(memory.get("access_count", 0), 100) / 100.0

        created_str = memory.get("created_at", "")
        time_score = 0.5
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                days_diff = (now - created).days
                time_score = max(0.0, 1.0 - days_diff / 180.0)
            except (ValueError, TypeError):
                pass

        content = memory.get("content", "")
        keyword_score = 0.0
        if query and content:
            query_lower = query.lower()
            content_lower = content.lower()
            query_terms = query_lower.split()
            if query_terms:
                matches = sum(1 for term in query_terms if term in content_lower)
                keyword_score = matches / len(query_terms)

        return (
            importance * 0.4 +
            access_count * 0.2 +
            time_score * 0.2 +
            keyword_score * 0.2
        )

    async def search_all_types(
        self,
        query: str,
        limit: int = 10,
    ) -> dict[str, list[dict]]:
        """按类型检索所有记忆

        Args:
            query: 搜索关键词
            limit: 每种类型返回数量上限

        Returns:
            dict: 按类型分组的检索结果
        """
        results = {}
        for mem_type in MemoryType:
            results[mem_type.value] = await self.hybrid_search(
                query, limit, mem_type,
            )
        return results