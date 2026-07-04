import pytest
from src.llm.base import BaseLLM
from src.models.message import ChatMessage, Role, StreamEvent, EventType


class MockLLM(BaseLLM):
    async def chat(self, messages: list[ChatMessage], **kwargs) -> str:
        return "mock response"

    async def chat_stream(self, messages: list[ChatMessage], **kwargs):
        yield StreamEvent(event_type=EventType.THOUGHT, content="mock ")
        yield StreamEvent(event_type=EventType.THOUGHT, content="stream")

    async def chat_with_tools(self, messages: list[ChatMessage], tools: list[dict], **kwargs) -> dict:
        return {"content": "mock tool response", "tool_calls": []}

    def count_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(len(m.content) for m in messages)

    async def close(self) -> None:
        pass


class TestBaseLLM:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseLLM()

    @pytest.mark.asyncio
    async def test_mock_llm_chat(self):
        llm = MockLLM()
        messages = [ChatMessage(role=Role.USER, content="hello")]
        result = await llm.chat(messages)
        assert result == "mock response"

    @pytest.mark.asyncio
    async def test_mock_llm_chat_stream(self):
        llm = MockLLM()
        messages = [ChatMessage(role=Role.USER, content="hello")]
        events = []
        async for event in llm.chat_stream(messages):
            events.append(event)
        assert len(events) == 2
        assert events[0].content == "mock "
        assert events[1].content == "stream"
        assert all(e.event_type == EventType.THOUGHT for e in events)

    @pytest.mark.asyncio
    async def test_mock_llm_chat_with_tools(self):
        llm = MockLLM()
        messages = [ChatMessage(role=Role.USER, content="search")]
        result = await llm.chat_with_tools(messages, tools=[])
        assert "content" in result
        assert "tool_calls" in result

    def test_mock_llm_count_tokens(self):
        llm = MockLLM()
        messages = [
            ChatMessage(role=Role.USER, content="hello"),
            ChatMessage(role=Role.ASSISTANT, content="world"),
        ]
        assert llm.count_tokens(messages) == 10

    @pytest.mark.asyncio
    async def test_mock_llm_close(self):
        llm = MockLLM()
        await llm.close()