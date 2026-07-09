"""CFA-Agent 情景记忆

记录成功的 ReAct 轨迹，供后续相似任务参考

技术方案 §7.9：
- 存储成功任务的完整 ReAct 轨迹
- 按任务相似度检索历史经验
- 在 think 阶段注入到 prompt 作为参考
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.common.types import MemoryType
from src.db.repository.memory_repo import MemoryRepository

logger = logging.getLogger("cfa-agent.memory.episodic")


class EpisodicMemory:
    """情景记忆

    职责：
    - 存储成功的 ReAct 执行轨迹
    - 按任务相似度检索历史轨迹
    - 支持轨迹回放和参考

    Attributes:
        _repo: 记忆数据访问层
    """

    def __init__(self, memory_repo: MemoryRepository):
        self._repo = memory_repo

    async def store_trajectory(
        self,
        task_id: str,
        task_description: str,
        steps: list[dict],
        agent_id: str | None = None,
        importance: float = 0.6,
    ) -> int | None:
        """存储执行轨迹

        Args:
            task_id: 任务 ID
            task_description: 任务描述
            steps: ReAct 步骤列表
            agent_id: 智能体 ID
            importance: 重要性分数 [0, 1]

        Returns:
            int | None: 记忆 ID，失败返回 None
        """
        content = json.dumps({
            "task_id": task_id,
            "task_description": task_description,
            "steps": steps,
        }, ensure_ascii=False)

        try:
            result = await self._repo.create(
                content=content,
                memory_type=MemoryType.EPISODIC,
                agent_id=agent_id,
                importance=importance,
            )
            if result:
                logger.info(f"Stored episodic memory for task {task_id}, id={result['id']}")
                return result["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to store episodic memory: {e}")
            return None

    async def retrieve_similar(
        self,
        query: str,
        limit: int = 5,
        agent_id: str | None = None,
    ) -> list[dict]:
        """检索相似任务的执行轨迹

        通过 FTS5 全文搜索找到描述相似的任务

        Args:
            query: 检索关键词
            limit: 返回结果数量上限
            agent_id: 限定特定智能体

        Returns:
            list[dict]: 相似记忆列表，包含解析后的轨迹
        """
        results = await self._repo.search_fts(query, limit)

        memories = []
        for row in results:
            if agent_id and row["agent_id"] != agent_id:
                continue
            try:
                parsed = json.loads(row["content"])
                memories.append({
                    "id": row["id"],
                    "memory_type": row["memory_type"],
                    "importance": row["importance"],
                    "task_id": parsed.get("task_id"),
                    "task_description": parsed.get("task_description"),
                    "steps": parsed.get("steps", []),
                    "created_at": row["created_at"],
                })
                await self._repo.update_access(row["id"])
            except json.JSONDecodeError:
                continue

        memories.sort(key=lambda m: m["importance"], reverse=True)
        return memories[:limit]

    async def get_by_task_id(self, task_id: str) -> dict | None:
        """根据任务 ID 获取记忆"""
        all_episodic = await self._repo.search_by_type(MemoryType.EPISODIC, limit=100)
        for memory in all_episodic:
            try:
                data = json.loads(memory["content"])
                if data.get("task_id") == task_id:
                    return {
                        **memory,
                        "parsed": data,
                    }
            except json.JSONDecodeError:
                continue
        return None