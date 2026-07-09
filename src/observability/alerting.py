"""CFA-Agent 告警通知

钉钉/企微/邮件告警
"""
from __future__ import annotations



class AlertingService:
    """告警通知服务

    职责：
    - 发送告警通知
    - 支持多种通知渠道（钉钉/企微/邮件）
    - 告警级别管理
    """

    def __init__(self):
        pass

    async def send_alert(
        self,
        title: str,
        message: str,
        level: str = "warning",
        channels: list[str] | None = None,
    ) -> bool:
        """发送告警

        Args:
            title: 告警标题
            message: 告警内容
            level: 告警级别 - info/warning/critical
            channels: 通知渠道列表

        Returns:
            bool: 是否发送成功
        """
        raise NotImplementedError