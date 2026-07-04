from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from src.common.config import get_config
from src.common.exceptions import LLMError, LLMRateLimitError
from src.common.logger import logger
from src.llm.base import BaseLLM
from src.llm.token_counter import TokenCounter
from src.models.message import ChatMessage, EventType, Role, StreamEvent

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class OpenAIAdapter(BaseLLM):
    def __init__(self):
        config = get_config()
        self.api_key = config.llm.api_key
        self.base_url = config.llm.base_url
        self.default_model = config.llm.model
        self.reasoning_model = config.llm.model_reasoning
        self.max_tokens = config.llm.max_tokens_per_request
        self.temperature = config.llm.temperature
        self._client: httpx.AsyncClient | None = None
        self._token_counter = TokenCounter()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=120.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> OpenAIAdapter:
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _build_messages_payload(self, messages: list[ChatMessage]) -> list[dict]:
        result = []
        for m in messages:
            entry: dict = {"role": m.role.value, "content": m.content}
            if m.role == Role.TOOL:
                tool_call_id = m.metadata.get("tool_call_id")
                if tool_call_id:
                    entry["tool_call_id"] = tool_call_id
            if m.role == Role.ASSISTANT:
                name = m.metadata.get("name")
                if name:
                    entry["name"] = name
                tool_calls = m.metadata.get("tool_calls")
                if tool_calls:
                    entry["tool_calls"] = tool_calls
            if m.role == Role.USER:
                name = m.metadata.get("name")
                if name:
                    entry["name"] = name
            result.append(entry)
        return result

    def _should_retry(self, status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    async def _retry_request(self, request_fn, *args, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await request_fn(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                last_exc = e
                if not self._should_retry(e.response.status_code):
                    raise
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "LLM request failed (status=%d), retrying in %.1fs (attempt %d/%d)",
                        e.response.status_code, delay, attempt + 1, _MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
            except (httpx.ReadError, httpx.StreamError) as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "LLM read/stream error, retrying in %.1fs (attempt %d/%d): %s",
                        delay, attempt + 1, _MAX_RETRIES, e,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise LLMError(detail={"error": str(e)}) from e
        if last_exc is not None:
            if isinstance(last_exc, httpx.HTTPStatusError):
                if last_exc.response.status_code == 429:
                    raise LLMRateLimitError(detail={"status_code": 429}) from last_exc
                raise LLMError(
                    detail={"status_code": last_exc.response.status_code, "body": last_exc.response.text}
                ) from last_exc
            raise LLMError(detail={"error": str(last_exc)}) from last_exc

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float | None = None,
        session_id: str | None = None,
        **kwargs,
    ) -> str:
        client = await self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": self._build_messages_payload(messages),
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.max_tokens,
            **kwargs,
        }

        async def _do_post():
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return resp

        try:
            resp = await self._retry_request(_do_post)
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            self._record_usage(usage, session_id=session_id)
            return content
        except (LLMError, LLMRateLimitError):
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(detail={"status_code": e.response.status_code, "body": e.response.text}) from e
        except httpx.RequestError as e:
            raise LLMError(detail={"error": str(e)})

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        session_id: str | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamEvent]:
        client = await self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": self._build_messages_payload(messages),
            "stream": True,
            **kwargs,
        }
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield StreamEvent(
                                    event_type=EventType.THOUGHT,
                                    content=content,
                                )
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise LLMRateLimitError(detail={"status_code": 429})
            raise LLMError(detail={"status_code": e.response.status_code})
        except (httpx.ReadError, httpx.StreamError) as e:
            raise LLMError(detail={"error": str(e)})
        except httpx.RequestError as e:
            raise LLMError(detail={"error": str(e)})

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict],
        model: str | None = None,
        session_id: str | None = None,
        **kwargs,
    ) -> dict:
        client = await self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": self._build_messages_payload(messages),
            "tools": tools,
            "tool_choice": "auto",
            **kwargs,
        }

        async def _do_post():
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return resp

        try:
            resp = await self._retry_request(_do_post)
            data = resp.json()
            msg = data["choices"][0]["message"]
            usage = data.get("usage", {})
            self._record_usage(usage, session_id=session_id)
            return {
                "content": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls", []),
            }
        except (LLMError, LLMRateLimitError):
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(detail={"status_code": e.response.status_code, "body": e.response.text}) from e
        except httpx.RequestError as e:
            raise LLMError(detail={"error": str(e)})

    def count_tokens(self, messages: list[ChatMessage]) -> int:
        text = "\n".join(f"{m.role.value}: {m.content}" for m in messages)
        return self._token_counter.estimate_tokens(text)

    def _record_usage(self, usage: dict, session_id: str | None = None) -> None:
        if not usage:
            return
        logger.debug(
            "LLM token usage - prompt: %s, completion: %s, total: %s",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0),
        )
        if session_id:
            self._token_counter.record(usage, session_id=session_id)