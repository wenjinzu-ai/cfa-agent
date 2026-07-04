from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.models.message import ChatMessage, StreamEvent


class BaseLLM(ABC):
    @abstractmethod
    async def chat(self, messages: list[ChatMessage], **kwargs) -> str:
        """非流式对话，返回完整回复文本"""

    @abstractmethod
    async def chat_stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[StreamEvent]:
        """流式对话，yield StreamEvent（THOUGHT 类型）"""

    @abstractmethod
    async def chat_with_tools(self, messages: list[ChatMessage], tools: list[dict], **kwargs) -> dict:
        """带工具选择的对话，返回 {content, tool_calls}"""

    @abstractmethod
    def count_tokens(self, messages: list[ChatMessage]) -> int:
        """估算消息列表的 Token 数"""

    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""