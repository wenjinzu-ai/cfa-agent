from __future__ import annotations

from src.common.logger import logger
from src.llm.base import BaseLLM
from src.llm.prompt_manager import PromptManager
from src.memory.sqlite_store import SQLiteStore
from src.models.memory import MemoryCategory, MemoryEntry, MemoryType


class Reflector:
    def __init__(self, store: SQLiteStore, llm: BaseLLM):
        self._store = store
        self._llm = llm

    async def evaluate_result(
        self, step_description: str, result: str, goal: str
    ) -> dict:
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/reflect",
            question=(
                f"目标：{goal}\n"
                f"当前步骤：{step_description}\n"
                f"执行结果：{result[:2000]}\n\n"
                f"请评估该步骤的执行结果是否令人满意，并给出改进建议。"
            ),
        )
        try:
            from src.models.message import ChatMessage, Role

            chat_messages = [
                ChatMessage(
                    role=Role(m.get("role", "user")), content=m.get("content", "")
                )
                for m in messages
            ]
            response = await self._llm.chat(chat_messages)
            is_satisfactory = "不满意" not in response and "失败" not in response[:100]
            return {
                "is_satisfactory": is_satisfactory,
                "analysis": response,
                "suggestion": "",
            }
        except Exception as e:
            logger.warning("反思评估失败: %s", e)
            return {"is_satisfactory": True, "analysis": "评估失败，默认满意", "suggestion": ""}

    async def analyze_strategy(
        self,
        plan_goal: str,
        completed_steps: list[dict],
        failed_steps: list[dict],
    ) -> str:
        summary = f"目标：{plan_goal}\n"
        summary += f"已完成 {len(completed_steps)} 步，失败 {len(failed_steps)} 步\n"
        for s in failed_steps[-3:]:
            summary += f"  失败步骤：{s.get('description', '')} - {s.get('result', '')}\n"
        prompt_mgr = PromptManager.get_instance()
        messages = prompt_mgr.build_messages(
            "reasoning/cot",
            question=f"以下任务执行策略是否有效？请分析并给出改进建议：\n{summary}",
        )
        try:
            from src.models.message import ChatMessage, Role

            chat_messages = [
                ChatMessage(
                    role=Role(m.get("role", "user")), content=m.get("content", "")
                )
                for m in messages
            ]
            return await self._llm.chat(chat_messages)
        except Exception as e:
            logger.warning("策略分析失败: %s", e)
            return "策略分析失败，建议继续当前策略"

    async def save_experience(
        self, task_description: str, outcome: str, tags: list[str] | None = None
    ) -> int:
        entry = MemoryEntry(
            type=MemoryType.LONG_TERM,
            category=MemoryCategory.EXPERIENCE,
            content=f"任务: {task_description}\n结果: {outcome}",
            tags=tags or [],
        )
        return await self._store.add_memory_entry(entry.to_db_dict())