"""CFA-Agent 多模型路由

推理层/执行层/备选层三层模型路由策略
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.common.settings import get_config
from src.llm.adapter import LLMAdapter

logger = logging.getLogger("cfa-agent.llm.router")


class LLMRouter:
    """多模型路由

    职责：
    - 推理层（reasoning）：复杂推理、规划（gpt-4o 等）
    - 执行层（execution）：工具调用、简单任务（gpt-4o-mini 等）
    - 备选层（fallback）：主模型不可用时的降级方案

    Attributes:
        _adapters: 各层模型适配器
    """

    def __init__(self, adapter: Optional[LLMAdapter] = None):
        """初始化路由

        Args:
            adapter: 共享的 LLM 适配器实例
        """
        self.config = get_config()
        self._adapter = adapter or LLMAdapter()
        self._models = {
            "reasoning": self.config.openai_model_reasoning,
            "execution": self.config.openai_model,
            "fallback": self.config.openai_model,
        }

    def get_model(self, task_type: str = "execution") -> str:
        """根据任务类型获取模型

        Args:
            task_type: 任务类型 - reasoning / execution / fallback

        Returns:
            str: 模型名称
        """
        return self._models.get(task_type, self._models["execution"])

    async def route_chat(
        self,
        messages: list[dict],
        task_type: str = "execution",
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> dict:
        """路由聊天请求到合适的模型

        Args:
            messages: 消息列表
            task_type: 任务类型
            tools: 工具列表
            temperature: 温度参数
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        model = self.get_model(task_type)

        try:
            if tools:
                return await self._adapter.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    model=model,
                    temperature=temperature,
                    **kwargs,
                )
            else:
                return await self._adapter.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    **kwargs,
                )
        except Exception as e:
            if task_type != "fallback":
                logger.warning(f"Primary model failed, falling back: {e}")
                return await self.route_chat(
                    messages=messages,
                    task_type="fallback",
                    tools=tools,
                    temperature=temperature,
                    **kwargs,
                )
            raise RuntimeError(f"所有模型均不可用: {str(e)}") from e

    async def route_think(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        """路由 think 节点请求

        think 节点使用执行层模型（gpt-4o-mini），因为主要是工具调用决策

        Args:
            messages: 消息列表
            tools: 可用工具列表
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        return await self.route_chat(
            messages=messages,
            task_type="execution",
            tools=tools,
            temperature=0.1,
            **kwargs,
        )

    async def route_reflect(
        self,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """路由 reflect 节点请求

        reflect 节点使用推理层模型（gpt-4o），因为需要深度分析

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        return await self.route_chat(
            messages=messages,
            task_type="reasoning",
            temperature=0.5,
            **kwargs,
        )

    async def route_answer(
        self,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """路由 answer 节点请求

        answer 节点使用推理层模型，因为需要高质量汇总

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        return await self.route_chat(
            messages=messages,
            task_type="reasoning",
            temperature=0.7,
            **kwargs,
        )

    async def route_verify(
        self,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """路由 verify 节点请求

        verify 节点使用推理层模型，因为需要严格判断结果质量。
        低温度 (0.1) 保证判断一致性。

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        return await self.route_chat(
            messages=messages,
            task_type="reasoning",
            temperature=0.1,
            response_format={"type": "json_object"},
            **kwargs,
        )

    async def route_classify(
        self,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """路由意图分类请求

        意图分类使用执行层模型，低温度保证分类一致性，
        response_format=json_object 保证输出可解析的 JSON。

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            dict: LLM 响应
        """
        return await self.route_chat(
            messages=messages,
            task_type="execution",
            temperature=0.0,
            response_format={"type": "json_object"},
            **kwargs,
        )