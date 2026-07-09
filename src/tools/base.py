"""CFA-Agent BaseTool 抽象类

基于 LangChain BaseTool 扩展，所有工具的基类。
工具 = 元数据声明 + Function Calling Schema + 执行逻辑 + 生命周期钩子

设计要点：
- 继承 langchain_core.tools.BaseTool，与 LangChain 生态无缝集成
- 通过 to_openai_schema() 方法生成标准 Function Calling Schema
- think 节点调用 ChatModel.bind_tools(tools) 将工具列表传给 LLM
- LLM 原生返回 tool_calls，从根本上消除工具名称幻觉和参数格式错误
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Type

from langchain_core.tools import BaseTool as LangChainBaseTool
from pydantic import BaseModel

from src.common.types import ToolSource, ToolStatus


class BaseTool(LangChainBaseTool):
    """工具抽象基类

    继承 LangChain BaseTool，与 LangChain 生态无缝集成。
    同时扩展了 CFA-Agent 特有属性（source, status, version, usage_count）。

    子类必须实现：
    - name: 工具名称（唯一标识）
    - description: 工具描述
    - args_schema: 参数 Pydantic Model（LangChain 标准）
    - _arun: 异步执行逻辑（LangChain 标准）

    子类可选覆写：
    - on_before_execute: 执行前钩子
    - on_after_execute: 执行后钩子
    - on_error: 错误处理钩子
    """

    source: ToolSource = ToolSource.BUILTIN
    status: ToolStatus = ToolStatus.ACTIVE
    version: str = "1.0.0"
    usage_count: int = 0

    args_schema: Type[BaseModel] = BaseModel

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.source = kwargs.get("source", ToolSource.BUILTIN)
        self.status = kwargs.get("status", ToolStatus.ACTIVE)
        self.version = kwargs.get("version", "1.0.0")
        self.usage_count = kwargs.get("usage_count", 0)

    @property
    def parameters_schema(self) -> dict:
        """参数 JSON Schema

        符合 JSON Schema 规范，定义工具输入参数的结构。
        从 args_schema 的 Pydantic model 自动生成。
        """
        if self.args_schema is not None and self.args_schema is not BaseModel:
            try:
                return self.args_schema.model_json_schema()
            except Exception:
                pass
        return {"type": "object", "properties": {}, "required": []}

    async def _arun(self, **kwargs: Any) -> Any:
        """LangChain 异步执行入口

        委托给子类的 execute 方法。
        """
        return await self.execute(**kwargs)

    def _run(self, **kwargs: Any) -> Any:
        """LangChain 同步执行入口（不推荐使用）

        抛出 NotImplementedError，CFA-Agent 全部使用异步。
        """
        raise NotImplementedError("CFA-Agent 只支持异步执行，请使用 _arun")

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """核心执行逻辑（异步）

        Args:
            **kwargs: 与 args_schema 定义一致的输入参数

        Returns:
            Any: 工具执行结果
        """
        ...

    def to_openai_schema(self) -> dict:
        """生成 OpenAI Function Calling Schema

        自动将工具元数据转换为标准 Function Calling 格式，
        使用 parameters_schema 作为参数定义来源。

        Returns:
            dict: 标准 Function Calling Schema
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    async def on_before_execute(self, **kwargs: Any) -> None:
        """执行前钩子"""

    async def on_after_execute(self, result: Any, **kwargs: Any) -> None:
        """执行后钩子"""

    async def on_error(self, error: Exception, **kwargs: Any) -> None:
        """错误处理钩子"""

    async def safe_execute(self, **kwargs: Any) -> dict:
        """安全执行工具

        封装 execute 方法，提供生命周期钩子调用和错误处理

        Returns:
            dict: 包含执行结果或错误信息的字典
        """
        self.usage_count += 1
        try:
            await self.on_before_execute(**kwargs)
            result = await self._arun(**kwargs)
            await self.on_after_execute(result, **kwargs)
            return {
                "tool_name": self.name,
                "status": "success",
                "result": result,
            }
        except Exception as e:
            await self.on_error(e, **kwargs)
            return {
                "tool_name": self.name,
                "status": "error",
                "error": str(e),
            }

    def is_available(self) -> bool:
        """工具是否可用"""
        return self.status == ToolStatus.ACTIVE

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source.value,
            "status": self.status.value,
            "version": self.version,
            "usage_count": self.usage_count,
            "parameters_schema": self.parameters_schema,
        }

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}("
            f"name={self.name}, source={self.source.value}, "
            f"status={self.status.value})>"
        )