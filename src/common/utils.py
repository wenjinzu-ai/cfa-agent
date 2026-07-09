"""CFA-Agent 公共工具函数"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def generate_id() -> str:
    """生成唯一 ID"""
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


def truncate_text(text: str, max_length: int = 200) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."