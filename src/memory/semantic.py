"""CFA-Agent 语义记忆

存储领域知识和概念，支持语义检索

技术方案 §7.9：
- 存储领域知识、概念、事实
- 支持语义检索（FTS5 关键词 + 内容相似度）
- 知识图谱式关联
"""
from __future__ import annotations

import json
import logging

from src.common.types import MemoryType
from src.db.repository.memory_repo import MemoryRepository

logger = logging.getLogger("cfa-agent.memory.semantic")


class SemanticMemory:
    """语义记忆

    职责：
    - 存储领域知识、概念、事实
    - 支持语义检索
    - 知识图谱式关联

    Attributes:
        _repo: 记忆数据访问层
    """

    def __init__(self, memory_repo: MemoryRepository):
        self._repo = memory_repo

    async def store_knowledge(
        self,
        content: str,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        importance: float = 0.5,
    ) -> int | None:
        """存储知识

        Args:
            content: 知识内容
            tags: 标签列表
            agent_id: 智能体 ID
            importance: 重要性分数

        Returns:
            int | None: 记忆 ID
        """
        enriched = json.dumps({
            "content": content,
            "tags": tags or [],
        }, ensure_ascii=False)

        try:
            result = await self._repo.create(
                content=enriched,
                memory_type=MemoryType.SEMANTIC,
                agent_id=agent_id,
                importance=importance,
            )
            if result:
                logger.info(f"Stored semantic memory: {content[:50]}...")
                return result["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to store semantic memory: {e}")
            return None

    async def retrieve_knowledge(
        self,
        query: str,
        limit: int = 10,
        agent_id: str | None = None,
    ) -> list[dict]:
        """检索知识

        Args:
            query: 检索关键词
            limit: 返回数量上限
            agent_id: 限定特定智能体

        Returns:
            list[dict]: 匹配的知识列表
        """
        results = await self._repo.search_fts(query, limit * 2)

        knowledge = []
        for row in results:
            if agent_id and row["agent_id"] != agent_id:
                continue
            try:
                parsed = json.loads(row["content"])
                knowledge.append({
                    "id": row["id"],
                    "memory_type": row["memory_type"],
                    "importance": row["importance"],
                    "content": parsed.get("content", ""),
                    "tags": parsed.get("tags", []),
                    "created_at": row["created_at"],
                })
                await self._repo.update_access(row["id"])
            except json.JSONDecodeError:
                continue

        knowledge.sort(key=lambda k: k["importance"], reverse=True)
        return knowledge[:limit]

    async def get_by_tag(self, tag: str, limit: int = 10) -> list[dict]:
        """按标签检索知识"""
        all_semantic = await self._repo.search_by_type(MemoryType.SEMANTIC, limit=100)
        results = []
        for memory in all_semantic:
            try:
                data = json.loads(memory["content"])
                if tag in data.get("tags", []):
                    results.append({
                        "id": memory["id"],
                        "content": data.get("content", ""),
                        "tags": data.get("tags", []),
                        "importance": memory["importance"],
                    })
            except json.JSONDecodeError:
                continue
        results.sort(key=lambda r: r["importance"], reverse=True)
        return results[:limit]