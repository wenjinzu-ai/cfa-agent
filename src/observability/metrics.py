"""CFA-Agent 指标采集

Prometheus 格式指标
"""
from __future__ import annotations



class MetricsCollector:
    """指标采集器

    职责：
    - 采集系统运行指标
    - Prometheus 格式输出
    - 任务/智能体/工具级别指标
    """

    def __init__(self):
        pass

    def record_task_duration(self, task_id: str, duration_ms: int, status: str) -> None:
        """记录任务执行时长"""
        raise NotImplementedError

    def record_tool_call(self, tool_name: str, duration_ms: int, status: str) -> None:
        """记录工具调用"""
        raise NotImplementedError

    def record_agent_status(self, agent_id: str, status: str) -> None:
        """记录智能体状态变更"""
        raise NotImplementedError

    def get_prometheus_metrics(self) -> str:
        """获取 Prometheus 格式指标"""
        raise NotImplementedError