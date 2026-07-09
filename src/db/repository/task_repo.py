"""CFA-Agent 任务 Repository

封装 tasks 表的数据访问操作
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import DatabaseConnection
from src.db.repository.base_repo import BaseRepository
from src.common.types import TaskStatus, IntrospectionState, ExecutionMode


class TaskRepository(BaseRepository):
    """任务 Repository"""

    def __init__(self, db: DatabaseConnection):
        super().__init__(db)

    async def create(
        self,
        task_id: str,
        description: str,
        session_id: str | None = None,
        conversation_index: int = 0,
        mode: ExecutionMode = ExecutionMode.SYNC,
        priority: int = 0,
        max_iterations: int = 20,
        uploaded_files: list | None = None,
        parent_task_id: str | None = None,
    ) -> dict:
        """创建任务"""
        await self.execute(
            """
            INSERT INTO tasks (
                id, parent_task_id, session_id, conversation_index, mode,
                description, status, priority, max_iterations, uploaded_files
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                parent_task_id,
                session_id,
                conversation_index,
                mode.value,
                description,
                TaskStatus.PENDING.value,
                priority,
                max_iterations,
                self._json_dumps(uploaded_files),
            ),
        )
        await self.commit()
        return await self.get_by_id(task_id)

    async def get_by_id(self, task_id: str) -> dict | None:
        """根据 ID 获取任务"""
        row = await self.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if row:
            row["plan"] = self._json_loads(row.get("plan"))
            row["result"] = self._json_loads(row.get("result"))
            row["cached_result"] = self._json_loads(row.get("cached_result"))
            row["uploaded_files"] = self._json_loads(row.get("uploaded_files"))
        return row

    async def get_by_session(self, session_id: str) -> list[dict]:
        """根据会话 ID 获取任务列表"""
        rows = await self.fetch_all(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY conversation_index",
            (session_id,),
        )
        for row in rows:
            row["plan"] = self._json_loads(row.get("plan"))
            row["result"] = self._json_loads(row.get("result"))
            row["cached_result"] = self._json_loads(row.get("cached_result"))
            row["uploaded_files"] = self._json_loads(row.get("uploaded_files"))
        return rows

    async def get_by_status(self, status: TaskStatus) -> list[dict]:
        """根据状态获取任务列表"""
        rows = await self.fetch_all(
            "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at",
            (status.value,),
        )
        for row in rows:
            row["plan"] = self._json_loads(row.get("plan"))
            row["result"] = self._json_loads(row.get("result"))
            row["cached_result"] = self._json_loads(row.get("cached_result"))
            row["uploaded_files"] = self._json_loads(row.get("uploaded_files"))
        return rows

    async def get_sub_tasks(self, parent_task_id: str) -> list[dict]:
        """获取子任务列表"""
        rows = await self.fetch_all(
            "SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY created_at",
            (parent_task_id,),
        )
        for row in rows:
            row["plan"] = self._json_loads(row.get("plan"))
            row["result"] = self._json_loads(row.get("result"))
            row["cached_result"] = self._json_loads(row.get("cached_result"))
            row["uploaded_files"] = self._json_loads(row.get("uploaded_files"))
        return rows

    async def update_status(self, task_id: str, status: TaskStatus) -> bool:
        """更新任务状态"""
        completed_at = None
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            completed_at = datetime.now(timezone.utc).isoformat()

        if completed_at:
            await self.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status.value, completed_at, task_id),
            )
        else:
            await self.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status.value, task_id),
            )
        await self.commit()
        return True

    async def update_introspection_state(
        self, task_id: str, state: IntrospectionState
    ) -> bool:
        """更新内省状态"""
        await self.execute(
            "UPDATE tasks SET introspection_state = ? WHERE id = ?",
            (state.value, task_id),
        )
        await self.commit()
        return True

    async def assign_agent(self, task_id: str, agent_id: str) -> bool:
        """分配智能体"""
        await self.execute(
            "UPDATE tasks SET assigned_agent_id = ?, status = ? WHERE id = ?",
            (agent_id, TaskStatus.ASSIGNED.value, task_id),
        )
        await self.commit()
        return True

    async def update_result(self, task_id: str, result: dict) -> bool:
        """更新任务结果"""
        await self.execute(
            "UPDATE tasks SET result = ? WHERE id = ?",
            (self._json_dumps(result), task_id),
        )
        await self.commit()
        return True

    async def update_plan(self, task_id: str, plan: dict) -> bool:
        """更新执行计划"""
        await self.execute(
            "UPDATE tasks SET plan = ? WHERE id = ?",
            (self._json_dumps(plan), task_id),
        )
        await self.commit()
        return True

    async def increment_iteration(self, task_id: str) -> int:
        """增加迭代次数并返回新值"""
        await self.execute(
            "UPDATE tasks SET iteration_count = iteration_count + 1 WHERE id = ?",
            (task_id,),
        )
        await self.commit()
        row = await self.fetch_one(
            "SELECT iteration_count FROM tasks WHERE id = ?", (task_id,)
        )
        return row["iteration_count"] if row else 0

    async def set_waiting_question(self, task_id: str, question: str) -> bool:
        """设置等待用户问题"""
        await self.execute(
            "UPDATE tasks SET waiting_question = ?, status = ? WHERE id = ?",
            (question, TaskStatus.WAITING_USER.value, task_id),
        )
        await self.commit()
        return True

    async def cache_result(
        self, task_id: str, result: dict, expires_at: str | None = None
    ) -> bool:
        """缓存异步结果"""
        await self.execute(
            "UPDATE tasks SET cached_result = ?, result_expires_at = ? WHERE id = ?",
            (self._json_dumps(result), expires_at, task_id),
        )
        await self.commit()
        return True

    async def delete(self, task_id: str) -> bool:
        """删除任务"""
        await self.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self.commit()
        return True

    async def list_recent(self, limit: int = 50) -> list[dict]:
        """获取最近的任务列表"""
        rows = await self.fetch_all(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for row in rows:
            row["plan"] = self._json_loads(row.get("plan"))
            row["result"] = self._json_loads(row.get("result"))
            row["cached_result"] = self._json_loads(row.get("cached_result"))
            row["uploaded_files"] = self._json_loads(row.get("uploaded_files"))
        return rows