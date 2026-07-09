"""CFA-Agent Token 计数器

基于 tiktoken 实现 Token 计数，用于上下文窗口管理
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("cfa-agent.llm.token_counter")

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
}

DEFAULT_CONTEXT_LIMIT = 128000
SAFETY_MARGIN = 0.1


class TokenCounter:
    """Token 计数器

    职责：
    - 计算文本的 Token 数量
    - 支持不同模型的 Token 计算
    - 上下文窗口管理（溢出检测、历史压缩）

    Attributes:
        _model: 模型名称
        _max_context: 最大上下文窗口
    """

    def __init__(self, model: str = "gpt-4o-mini", max_context: Optional[int] = None):
        self._model = model
        self._max_context = max_context or self._get_context_limit(model)
        self._encoding = None

    def _get_context_limit(self, model: str) -> int:
        """获取模型的上下文窗口大小"""
        for key, limit in MODEL_CONTEXT_LIMITS.items():
            if key in model.lower():
                return limit
        return DEFAULT_CONTEXT_LIMIT

    def _get_encoding(self):
        """延迟加载 tiktoken encoding"""
        if self._encoding is None:
            try:
                import tiktoken
                try:
                    self._encoding = tiktoken.encoding_for_model(self._model)
                except KeyError:
                    self._encoding = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                logger.warning("tiktoken not installed, using approximate token counting")
                self._encoding = None
        return self._encoding

    def count(self, text: str) -> int:
        """计算文本的 Token 数量

        Args:
            text: 输入文本

        Returns:
            int: Token 数量
        """
        if not text:
            return 0

        encoding = self._get_encoding()
        if encoding is not None:
            return len(encoding.encode(text))

        return max(1, len(text) // 4)

    def count_messages(self, messages: list[dict]) -> int:
        """计算消息列表的 Token 数量

        每条消息额外消耗约 4 个 token（格式化开销）
        参考 OpenAI 官方文档

        Args:
            messages: OpenAI 格式消息列表

        Returns:
            int: Token 数量
        """
        total = 0
        for msg in messages:
            total += 4
            total += self.count(msg.get("content", ""))
            total += self.count(msg.get("role", ""))
            if msg.get("name"):
                total += self.count(msg["name"])
                total += 1
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    total += self.count(tc.get("function", {}).get("name", ""))
                    total += self.count(str(tc.get("function", {}).get("arguments", "")))
        total += 2
        return total

    def truncate_to_limit(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 Token 限制

        Args:
            text: 输入文本
            max_tokens: 最大 token 数

        Returns:
            str: 截断后的文本
        """
        if not text:
            return text

        encoding = self._get_encoding()
        if encoding is not None:
            tokens = encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return encoding.decode(tokens[:max_tokens])

        char_limit = max_tokens * 4
        if len(text) <= char_limit:
            return text
        return text[:char_limit]

    def is_overflow(self, messages: list[dict], reserved_for_response: int = 4096) -> bool:
        """检查消息列表是否超出上下文窗口

        Args:
            messages: 消息列表
            reserved_for_response: 为响应预留的 token 数

        Returns:
            bool: 是否溢出
        """
        used = self.count_messages(messages)
        limit = int(self._max_context * (1 - SAFETY_MARGIN)) - reserved_for_response
        return used > limit

    def get_available_tokens(self, messages: list[dict], reserved_for_response: int = 4096) -> int:
        """获取剩余可用 token 数

        Args:
            messages: 当前消息列表
            reserved_for_response: 为响应预留的 token 数

        Returns:
            int: 剩余可用 token 数
        """
        used = self.count_messages(messages)
        limit = int(self._max_context * (1 - SAFETY_MARGIN)) - reserved_for_response
        return max(0, limit - used)

    def compress_history(self, messages: list[dict], keep_recent: int = 4) -> list[dict]:
        """压缩消息历史

        保留 system 消息和最近 N 条消息，中间消息替换为摘要

        Args:
            messages: 原始消息列表
            keep_recent: 保留最近的消息数

        Returns:
            list[dict]: 压缩后的消息列表
        """
        if len(messages) <= keep_recent + 1:
            return messages

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= keep_recent:
            return messages

        recent = non_system[-keep_recent:]
        older = non_system[:-keep_recent]

        summary_parts = []
        for msg in older:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                summary_parts.append(f"[{role}]: {content[:200]}")

        summary = "Earlier conversation summary:\n" + "\n".join(summary_parts)

        compressed = system_msgs + [
            {"role": "system", "content": summary}
        ] + recent

        return compressed