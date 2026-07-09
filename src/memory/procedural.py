"""CFA-Agent 程序性记忆

存储成功策略和操作流程，按场景匹配推荐策略

技术方案 §7.9：
- 存储成功策略和操作流程
- 按场景匹配推荐策略
- 策略优化和迭代
"""
from __future__ import annotations

import json
import logging

from src.common.types import MemoryType
from src.db.repository.memory_repo import MemoryRepository

logger = logging.getLogger("cfa-agent.memory.procedural")


class ProceduralMemory:
    """程序性记忆

    职责：
    - 存储成功策略和操作流程
    - 按场景匹配推荐策略
    - 策略优化和迭代

    Attributes:
        _repo: 记忆数据访问层
    """

    def __init__(self, memory_repo: MemoryRepository):
        self._repo = memory_repo

    async def store_strategy(
        self,
        name: str,
        steps: list[str],
        context: str,
        agent_id: str | None = None,
        importance: float = 0.7,
        success_rate: float = 1.0,
    ) -> int | None:
        """存储策略

        Args:
            name: 策略名称
            steps: 步骤列表
            context: 适用场景
            agent_id: 智能体 ID
            importance: 重要性分数
            success_rate: 成功率 [0, 1]

        Returns:
            int | None: 记忆 ID
        """
        content = json.dumps({
            "name": name,
            "steps": steps,
            "context": context,
            "success_rate": success_rate,
        }, ensure_ascii=False)

        try:
            result = await self._repo.create(
                content=content,
                memory_type=MemoryType.PROCEDURAL,
                agent_id=agent_id,
                importance=importance,
            )
            if result:
                logger.info(f"Stored procedural memory: {name}")
                return result["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to store procedural memory: {e}")
            return None

    async def retrieve_strategy(
        self,
        context: str,
        limit: int = 5,
        agent_id: str | None = None,
    ) -> list[dict]:
        """检索匹配策略

        Args:
            context: 场景描述
            limit: 返回数量上限
            agent_id: 限定特定智能体

        Returns:
            list[dict]: 匹配的策略列表
        """
        results = await self._repo.search_fts(context, limit * 2)

        strategies = []
        for row in results:
            if agent_id and row["agent_id"] != agent_id:
                continue
            try:
                parsed = json.loads(row["content"])
                strategies.append({
                    "id": row["id"],
                    "memory_type": row["memory_type"],
                    "importance": row["importance"],
                    "name": parsed.get("name", ""),
                    "steps": parsed.get("steps", []),
                    "context": parsed.get("context", ""),
                    "success_rate": parsed.get("success_rate", 1.0),
                    "created_at": row["created_at"],
                })
                await self._repo.update_access(row["id"])
            except json.JSONDecodeError:
                continue

        strategies.sort(key=lambda s: s["importance"] * s["success_rate"], reverse=True)
        return strategies[:limit]

    async def update_success_rate(self, strategy_id: int, success_rate: float) -> bool:
        """更新策略成功率

        Args:
            strategy_id: 策略 ID
            success_rate: 新的成功率

        Returns:
            bool: 是否更新成功
        """
        strategy = await self._repo.get_by_id(strategy_id)
        if not strategy:
            return False

        try:
            data = json.loads(strategy["content"])
            data["success_rate"] = success_rate
            new_content = json.dumps(data, ensure_ascii=False)

            await self._repo.update_importance(
                strategy_id,
                max(0.1, strategy["importance"] * success_rate),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update strategy success rate: {e}")
            return False