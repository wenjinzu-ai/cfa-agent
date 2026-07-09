"""CFA-Agent 多模型适配器

基于 litellm 实现多模型统一调用接口
支持 OpenAI / Anthropic / 本地模型等
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Optional

import litellm

from src.common.settings import get_config

logger = logging.getLogger("cfa-agent.llm")


class LLMAdapter:
    """多模型适配器

    职责：
    - 基于 litellm 统一调用不同 LLM
    - 支持 OpenAI / Anthropic / 本地模型等
    - 提供同步和流式调用接口
    - 自动处理重试和错误

    Attributes:
        config: 全局配置
        _model: 当前使用的模型名称
        _api_key: API 密钥
        _base_url: API 基础 URL
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """初始化适配器

        Args:
            model: 模型名称（默认从配置读取）
            api_key: API 密钥（默认从配置读取）
            base_url: API 基础 URL（默认从配置读取）
        """
        self.config = get_config()
        self._model = model or self.config.openai_model
        self._api_key = api_key or self.config.openai_api_key
        self._base_url = base_url or self.config.openai_base_url

    @property
    def model(self) -> str:
        return self._model

    def _normalize_model_name(self, model_name: str) -> str:
        """标准化模型名，为非标准/第三方 OpenAI 兼容模型添加 openai/ 前缀"""
        if "/" in model_name:
            return model_name
        known_providers = {"gpt-", "claude", "gemini", "command", "mistral", "codellama"}
        for prefix in known_providers:
            if model_name.lower().startswith(prefix):
                return model_name
        return f"openai/{model_name}"

    def _build_completion_kwargs(self, model_name: str, extra: dict) -> dict:
        """构建 litellm.acompletion 参数字典"""
        kwargs = {
            "model": self._normalize_model_name(model_name),
            "api_key": self._api_key,
        }
        if self._base_url:
            kwargs["api_base"] = self._base_url
        kwargs.update(extra)
        return kwargs

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict:
        """同步聊天调用

        Args:
            messages: 消息列表（OpenAI 格式）
            model: 模型名称（可选，覆盖默认）
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他 litellm 参数

        Returns:
            dict: LLM 响应
        """
        start_time = time.time()
        model_name = model or self._model

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    **self._build_completion_kwargs(model_name, {
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }),
                    **kwargs,
                ),
                timeout=120.0,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"LLM call completed in {duration_ms}ms")

            return {
                "content": getattr(response.choices[0].message, "content", "") or "",
                "tool_calls": getattr(response.choices[0].message, "tool_calls", None),
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "model": response.model,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"LLM 调用失败: {str(e)}") from e

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """流式聊天调用

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Yields:
            dict: 流式响应块
        """
        model_name = model or self._model

        try:
            response_stream = await litellm.acompletion(
                **self._build_completion_kwargs(model_name, {
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                }),
                **kwargs,
            )

            async for chunk in response_stream:
                yield {
                    "content": chunk.choices[0].delta.content or "",
                    "finish_reason": chunk.choices[0].finish_reason,
                }

        except Exception as e:
            logger.error(f"Streaming LLM call failed: {e}")
            raise RuntimeError(f"流式 LLM 调用失败: {str(e)}") from e

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
        **kwargs,
    ) -> dict:
        """带工具的聊天调用（Function Calling）

        Args:
            messages: 消息列表
            tools: 工具列表（OpenAI Function Calling 格式）
            model: 模型名称
            temperature: 温度参数
            tool_choice: 工具选择策略 (auto/none/required)
            **kwargs: 其他参数

        Returns:
            dict: 包含 content 和 tool_calls 的响应
        """
        start_time = time.time()
        model_name = model or self._model

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    **self._build_completion_kwargs(model_name, {
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": tool_choice,
                        "temperature": temperature,
                    }),
                    **kwargs,
                ),
                timeout=120.0,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            message = response.choices[0].message

            result = {
                "content": message.content or "",
                "tool_calls": [],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "model": response.model,
                "duration_ms": duration_ms,
            }

            if hasattr(message, "tool_calls") and message.tool_calls:
                import json
                for tc in message.tool_calls:
                    try:
                        args = (
                            json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments
                        )
                    except (json.JSONDecodeError, TypeError):
                        args = {"raw": str(tc.function.arguments)}
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": args,
                    })

            logger.debug(f"Tool call completed in {duration_ms}ms, got {len(result['tool_calls'])} tool calls")
            return result

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            raise RuntimeError(f"工具调用失败: {str(e)}") from e

    def format_messages_for_llm(self, history: list, system_prompt: str) -> list[dict]:
        """将 ReAct 历史格式化为 LLM 消息列表

        Args:
            history: ReAct 步骤历史
            system_prompt: 系统提示词

        Returns:
            list[dict]: OpenAI 格式的消息列表
        """
        messages = [{"role": "system", "content": system_prompt}]

        for step in history:
            if step.get("thought"):
                messages.append({
                    "role": "assistant",
                    "content": f"Thought: {step['thought']}",
                })

            if step.get("action"):
                action_str = f"Action: {step['action']}"
                messages.append({"role": "assistant", "content": action_str})

            if step.get("observation"):
                messages.append({
                    "role": "user",
                    "content": f"Observation: {step['observation']}",
                })

        return messages