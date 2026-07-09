"""CFA-Agent 记忆管理器

协调三种记忆类型的存取和检索，管理记忆生命周期

技术方案 §7.9：
- 协调情景记忆、语义记忆、程序性记忆
- 提供统一的存取接口
- 管理记忆生命周期（创建、访问、衰减、清理）
- 为 think 节点提供记忆检索服务
"""
from __future__ import annotations

import logging
from typing import Optional

from src.common.types import MemoryType
from src.db.repository.memory_repo import MemoryRepository
from src.memory.episodic import EpisodicMemory
from src.memory.procedural import ProceduralMemory
from src.memory.retrieval import MemoryRetrieval
from src.memory.semantic import SemanticMemory

logger = logging.getLogger("cfa-agent.memory.manager")


class MemoryManager:
    """记忆管理器

    职责：
    - 协调情景记忆、语义记忆、程序性记忆
    - 提供统一的存取接口
    - 管理记忆生命周期（创建、访问、衰减、清理）
    - 为 think 节点提供记忆检索服务（替代 Phase 2 的 MemoryStub）

    Attributes:
        _repo: 记忆数据访问层
        _episodic: 情景记忆
        _semantic: 语义记忆
        _procedural: 程序性记忆
        _retrieval: 检索策略
    """

    def __init__(self, memory_repo: MemoryRepository):
        self._repo = memory_repo
        self._episodic = EpisodicMemory(memory_repo)
        self._semantic = SemanticMemory(memory_repo)
        self._procedural = ProceduralMemory(memory_repo)
        self._retrieval = MemoryRetrieval(memory_repo)

    @property
    def episodic(self) -> EpisodicMemory:
        return self._episodic

    @property
    def semantic(self) -> SemanticMemory:
        return self._semantic

    @property
    def procedural(self) -> ProceduralMemory:
        return self._procedural

    @property
    def retrieval(self) -> MemoryRetrieval:
        return self._retrieval

    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        agent_id: str | None = None,
        importance: float = 0.5,
    ) -> int | None:
        """存储记忆（通用接口）

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            agent_id: 智能体 ID
            importance: 重要性分数

        Returns:
            int | None: 记忆 ID
        """
        try:
            result = await self._repo.create(
                content=content,
                memory_type=memory_type,
                agent_id=agent_id,
                importance=importance,
            )
            if result:
                logger.debug(f"Stored memory: type={memory_type.value}, id={result['id']}")
                return result["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return None

    async def retrieve(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        agent_id: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """检索记忆（通用接口）

        使用混合检索策略

        Args:
            query: 检索关键词
            memory_type: 记忆类型过滤
            agent_id: 智能体过滤
            limit: 返回数量上限

        Returns:
            list[dict]: 匹配的记忆列表
        """
        results = await self._retrieval.hybrid_search(query, limit, memory_type)

        if agent_id:
            results = [r for r in results if r.get("agent_id") == agent_id]

        return results

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """搜索相关记忆（think 节点接口，替代 MemoryStub）

        Args:
            query: 检索关键词
            top_k: 返回数量上限

        Returns:
            list[dict]: 相关记忆列表
        """
        results = await self._retrieval.hybrid_search(query, top_k)

        formatted = []
        for mem in results:
            formatted.append({
                "id": mem["id"],
                "type": mem["memory_type"],
                "content": mem["content"],
                "importance": mem["importance"],
                "created_at": mem["created_at"],
            })

        return formatted

    async def search_for_think(
        self,
        task: str,
        current_thought: str,
        top_k: int = 3,
    ) -> str:
        """为 think 节点检索并格式化记忆

        技术方案 §7.9：
        1. 以「当前任务描述 + 当前 thought」作为 Query
        2. 混合检索取 Top-K
        3. 格式化为 prompt 注入格式

        Args:
            task: 当前任务描述
            current_thought: 当前推理内容
            top_k: 返回记忆数量

        Returns:
            str: 格式化的记忆文本，注入到 prompt 中
        """
        query = f"{task} {current_thought}"
        memories = await self.search(query, top_k)

        if not memories:
            return "(暂无相关历史经验)"

        parts = [f"[相关历史经验]"]
        for i, mem in enumerate(memories):
            mem_type = mem.get("type", "unknown")
            content = mem.get("content", "")

            summary = content[:200] + "..." if len(content) > 200 else content

            if mem_type == "episodic":
                parts.append(f"- 经验{i + 1}：历史任务轨迹参考 - {summary}")
            elif mem_type == "semantic":
                parts.append(f"- 知识{i + 1}：领域知识 - {summary}")
            elif mem_type == "procedural":
                parts.append(f"- 策略{i + 1}：成功策略 - {summary}")
            else:
                parts.append(f"- 记忆{i + 1}：{summary}")

        return "\n".join(parts)

    async def store_successful_trajectory(
        self,
        task_id: str,
        task_description: str,
        steps: list[dict],
        agent_id: str | None = None,
    ) -> int | None:
        """存储成功的 ReAct 轨迹

        Args:
            task_id: 任务 ID
            task_description: 任务描述
            steps: ReAct 步骤
            agent_id: 智能体 ID

        Returns:
            int | None: 记忆 ID
        """
        return await self._episodic.store_trajectory(
            task_id=task_id,
            task_description=task_description,
            steps=steps,
            agent_id=agent_id,
        )

    async def decay(self, days: int = 90, min_importance: float = 0.3) -> int:
        """衰减旧记忆

        清理重要性低于阈值且超过指定天数的记忆

        Args:
            days: 天数阈值
            min_importance: 最低重要性

        Returns:
            int: 清理的记忆数量
        """
        count = await self._repo.delete_old_memories(days, min_importance)
        logger.info(f"Memory decay: removed {count} old memories")
        return count

    async def get_stats(self) -> dict:
        """获取记忆统计信息"""
        stats = {}
        for mem_type in MemoryType:
            memories = await self._repo.search_by_type(mem_type, limit=1000)
            stats[mem_type.value] = {
                "count": len(memories),
                "avg_importance": (
                    sum(m["importance"] for m in memories) / len(memories)
                    if memories else 0
                ),
            }
        return stats