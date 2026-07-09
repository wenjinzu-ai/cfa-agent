"""CFA-Agent 当前时间工具

大模型不知道当前时间，使用训练截止日期的时间。
此工具获取当前系统时间，支持时区和格式化。
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.tools.base import BaseTool


class CurrentTime(BaseTool):
    name: str = "current_time"
    description: str = (
        "Get the current date and time. "
        "Use this tool whenever you need to know the current time, "
        "today's date, or any time-related information. "
        "The model does not have access to real-time clock, "
        "so always call this tool before answering time-sensitive questions."
    )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone string (e.g. 'Asia/Shanghai', 'America/New_York'). Default: 'Asia/Shanghai'",
                    "default": "Asia/Shanghai",
                },
                "format": {
                    "type": "string",
                    "description": "Output format: 'iso' for ISO 8601, 'readable' for human-readable, 'all' for both. Default: 'all'",
                    "enum": ["iso", "readable", "all"],
                    "default": "all",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs) -> dict:
        tz_name = kwargs.get("timezone", "Asia/Shanghai")
        fmt = kwargs.get("format", "all")

        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
            tz_name = "UTC"

        now = datetime.now(tz)

        result = {"timezone": tz_name}

        if fmt in ("iso", "all"):
            result["iso"] = now.isoformat()

        if fmt in ("readable", "all"):
            result["readable"] = now.strftime("%Y年%m月%d日 %H:%M:%S")
            result["date"] = now.strftime("%Y-%m-%d")
            result["time"] = now.strftime("%H:%M:%S")
            result["weekday"] = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

        return result