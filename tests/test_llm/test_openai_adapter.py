import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm.openai_adapter import OpenAIAdapter, _MAX_RETRIES
from src.models.message import ChatMessage, Role, EventType
from src.common.exceptions import LLMError, LLMRateLimitError


@pytest.fixture
def adapter():
    with patch("src.llm.openai_adapter.get_config") as mock_cfg:
        cfg = MagicMock()
        cfg.llm.api_key = "test-key"
        cfg.llm.base_url = "https://api.openai.com/v1"
        cfg.llm.model = "gpt-4o-mini"
        cfg.llm.model_reasoning = "gpt-4o"
        cfg.llm.max_tokens_per_request = 4096
        cfg.llm.temperature = 0.7
        mock_cfg.return_value = cfg
        a = OpenAIAdapter()
        a._client = AsyncMock()
        a._client.is_closed = True
        yield a


def _make_messages():
    return [ChatMessage(role=Role.USER, content="hello")]


class TestOpenAIAdapterInit:
    def test_init_reads_config(self):
        with patch("src.llm.openai_adapter.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.llm.api_key = "sk-test"
            cfg.llm.base_url = "https://api.example.com/v1"
            cfg.llm.model = "gpt-4"
            cfg.llm.model_reasoning = "o1"
            cfg.llm.max_tokens_per_request = 2048
            cfg.llm.temperature = 0.5
            mock_cfg.return_value = cfg
            a = OpenAIAdapter()
            assert a.api_key == "sk-test"
            assert a.base_url == "https://api.example.com/v1"
            assert a.default_model == "gpt-4"
            assert a.reasoning_model == "o1"
            assert a.max_tokens == 2048
            assert a.temperature == 0.5


class TestOpenAIAdapterChat:
    @pytest.mark.asyncio
    async def test_chat_success(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        adapter._client = mock_client

        result = await adapter.chat(_make_messages())
        assert result == "Hello!"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_rate_limit(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "rate limited", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMRateLimitError):
            await adapter.chat(_make_messages())

    @pytest.mark.asyncio
    async def test_chat_server_error(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "server error", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMError):
            await adapter.chat(_make_messages())

    @pytest.mark.asyncio
    async def test_chat_connection_error(self, adapter):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("connection failed")
        )
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMError):
            await adapter.chat(_make_messages())

    @pytest.mark.asyncio
    async def test_chat_with_session_id_records_usage(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        adapter._client = mock_client

        result = await adapter.chat(_make_messages(), session_id="sess-1")
        assert result == "Hello!"
        usage = adapter._token_counter.get_session_usage("sess-1")
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 15


class TestOpenAIAdapterChatStream:
    @pytest.mark.asyncio
    async def test_chat_stream_success(self, adapter):
        lines = [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo!"}}]}',
            "data: [DONE]",
        ]

        async def _mock_aiter_lines():
            for line in lines:
                yield line

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = _mock_aiter_lines

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_cm)
        mock_client.is_closed = False
        adapter._client = mock_client

        events = []
        async for event in adapter.chat_stream(_make_messages()):
            events.append(event)

        assert len(events) == 2
        assert events[0].content == "Hel"
        assert events[1].content == "lo!"
        assert events[0].event_type == EventType.THOUGHT

    @pytest.mark.asyncio
    async def test_chat_stream_skips_malformed_data(self, adapter):
        lines = [
            "data: not json",
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]

        async def _mock_aiter_lines():
            for line in lines:
                yield line

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = _mock_aiter_lines

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_cm)
        mock_client.is_closed = False
        adapter._client = mock_client

        events = []
        async for event in adapter.chat_stream(_make_messages()):
            events.append(event)

        assert len(events) == 1
        assert events[0].content == "ok"

    @pytest.mark.asyncio
    async def test_chat_stream_rate_limit(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "rate limited", request=MagicMock(), response=mock_resp
            )
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_cm)
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMRateLimitError):
            async for _ in adapter.chat_stream(_make_messages()):
                pass

    @pytest.mark.asyncio
    async def test_chat_stream_read_error(self, adapter):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            side_effect=httpx.ReadError("read error", request=MagicMock())
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_cm)
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMError):
            async for _ in adapter.chat_stream(_make_messages()):
                pass


class TestOpenAIAdapterChatWithTools:
    @pytest.mark.asyncio
    async def test_chat_with_tools_success(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "web_search", "arguments": '{"query": "test"}'},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        adapter._client = mock_client

        tools = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
        result = await adapter.chat_with_tools(_make_messages(), tools=tools)
        assert result["content"] is None
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_chat_with_tools_no_tool_call(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "I can answer directly", "tool_calls": []}}],
            "usage": {},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        adapter._client = mock_client

        result = await adapter.chat_with_tools(_make_messages(), tools=[])
        assert result["content"] == "I can answer directly"
        assert result["tool_calls"] == []

    @pytest.mark.asyncio
    async def test_chat_with_tools_session_id_records_usage(self, adapter):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "done", "tool_calls": []}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        adapter._client = mock_client

        await adapter.chat_with_tools(_make_messages(), tools=[], session_id="sess-tools")
        usage = adapter._token_counter.get_session_usage("sess-tools")
        assert usage.total_tokens == 8


class TestOpenAIAdapterBuildMessagesPayload:
    def test_basic_messages(self, adapter):
        messages = [
            ChatMessage(role=Role.SYSTEM, content="system prompt"),
            ChatMessage(role=Role.USER, content="hello"),
            ChatMessage(role=Role.ASSISTANT, content="hi"),
        ]
        payload = adapter._build_messages_payload(messages)
        assert len(payload) == 3
        assert payload[0] == {"role": "system", "content": "system prompt"}
        assert payload[1] == {"role": "user", "content": "hello"}
        assert payload[2] == {"role": "assistant", "content": "hi"}

    def test_tool_role_with_tool_call_id(self, adapter):
        messages = [
            ChatMessage(
                role=Role.TOOL,
                content="tool result",
                metadata={"tool_call_id": "call_123"},
            ),
        ]
        payload = adapter._build_messages_payload(messages)
        assert payload[0]["role"] == "tool"
        assert payload[0]["tool_call_id"] == "call_123"

    def test_assistant_with_name_and_tool_calls(self, adapter):
        tool_calls = [{"id": "call_1", "type": "function", "function": {"name": "search"}}]
        messages = [
            ChatMessage(
                role=Role.ASSISTANT,
                content="",
                metadata={"name": "assistant_bot", "tool_calls": tool_calls},
            ),
        ]
        payload = adapter._build_messages_payload(messages)
        assert payload[0]["name"] == "assistant_bot"
        assert payload[0]["tool_calls"] == tool_calls

    def test_user_with_name(self, adapter):
        messages = [
            ChatMessage(
                role=Role.USER,
                content="hello",
                metadata={"name": "alice"},
            ),
        ]
        payload = adapter._build_messages_payload(messages)
        assert payload[0]["name"] == "alice"

    def test_tool_role_without_tool_call_id(self, adapter):
        messages = [
            ChatMessage(role=Role.TOOL, content="result"),
        ]
        payload = adapter._build_messages_payload(messages)
        assert "tool_call_id" not in payload[0]


class TestOpenAIAdapterCountTokens:
    def test_count_tokens(self, adapter):
        messages = [
            ChatMessage(role=Role.USER, content="hello world"),
            ChatMessage(role=Role.ASSISTANT, content="hi there"),
        ]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_empty(self, adapter):
        count = adapter.count_tokens([])
        assert count == 0


class TestOpenAIAdapterRecordUsage:
    def test_record_usage_with_session_id(self, adapter):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        adapter._record_usage(usage, session_id="test-session")
        result = adapter._token_counter.get_session_usage("test-session")
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15

    def test_record_usage_without_session_id(self, adapter):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        adapter._record_usage(usage)
        result = adapter._token_counter.get_session_usage("any-session")
        assert result.total_tokens == 0

    def test_record_usage_empty_dict(self, adapter):
        adapter._record_usage({}, session_id="test-session")
        result = adapter._token_counter.get_session_usage("test-session")
        assert result.total_tokens == 0

    def test_record_usage_accumulates(self, adapter):
        adapter._record_usage(
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_id="sess",
        )
        adapter._record_usage(
            {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            session_id="sess",
        )
        result = adapter._token_counter.get_session_usage("sess")
        assert result.prompt_tokens == 30
        assert result.completion_tokens == 15
        assert result.total_tokens == 45


class TestOpenAIAdapterRetry:
    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self, adapter):
        call_count = 0

        async def _mock_post(url, json=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.text = "Internal Server Error"
                raise httpx.HTTPStatusError("server error", request=MagicMock(), response=mock_resp)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "recovered!"}}],
                "usage": {},
            }
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = _mock_post
        mock_client.is_closed = False
        adapter._client = mock_client

        with patch("src.llm.openai_adapter.asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.chat(_make_messages())
        assert result == "recovered!"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_on_500(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "server error", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.is_closed = False
        adapter._client = mock_client

        with patch("src.llm.openai_adapter.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMError):
                await adapter.chat(_make_messages())

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "bad request", request=MagicMock(), response=mock_resp
            )
        )
        mock_client.is_closed = False
        adapter._client = mock_client

        with pytest.raises(LLMError):
            await adapter.chat(_make_messages())
        assert mock_client.post.call_count == 1


class TestOpenAIAdapterContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_initializes_client(self):
        with patch("src.llm.openai_adapter.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.llm.api_key = "test-key"
            cfg.llm.base_url = "https://api.openai.com/v1"
            cfg.llm.model = "gpt-4o-mini"
            cfg.llm.model_reasoning = "gpt-4o"
            cfg.llm.max_tokens_per_request = 4096
            cfg.llm.temperature = 0.7
            mock_cfg.return_value = cfg
            async with OpenAIAdapter() as adapter:
                assert adapter._client is not None
                assert not adapter._client.is_closed