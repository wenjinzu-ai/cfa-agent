"""CFA-Agent 自建 Trace 记录器

基于 SQLite react_steps 表记录执行轨迹
"""
from __future__ import annotations



class TraceLogger:
    """Trace 记录器

    职责：
    - 记录 ReAct 循环的每一步
    - 基于 SQLite react_steps 表
    - 支持轨迹查询和回放
    """

    def __init__(self):
        pass

    async def log_step(
        self,
        task_id: str,
        step_index: int,
        thought: str | None = None,
        action: dict | None = None,
        observation: str | None = None,
        duration_ms: int | None = None,
        status: str = "success",
    ) -> None:
        """记录执行步骤"""
        raise NotImplementedError

    async def get_trace(self, task_id: str) -> list[dict]:
        """获取任务的完整执行轨迹"""
        raise NotImplementedError