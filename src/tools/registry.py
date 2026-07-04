from __future__ import annotations

import threading
from typing import Type

from src.common.logger import logger
from src.tools.base import BaseTool
from src.models.tool import ToolDefinition


class ToolRegistry:
    _instance: ToolRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._registry: dict[str, Type[BaseTool]] = {}
        self._instances: dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, tool_class: Type[BaseTool]) -> Type[BaseTool]:
        instance = tool_class()
        name = instance.definition.name
        if name in self._instances:
            logger.warning("工具 %s 已注册，将被覆盖", name)
        self._registry[name] = tool_class
        self._instances[name] = instance
        return tool_class

    def get(self, name: str) -> BaseTool | None:
        return self._instances.get(name)

    def get_definition(self, name: str) -> ToolDefinition | None:
        inst = self._instances.get(name)
        return inst.definition if inst else None

    def list_tools(self) -> list[ToolDefinition]:
        return [inst.definition for inst in self._instances.values()]

    def list_schemas_for_llm(self) -> list[dict]:
        schemas = []
        for inst in self._instances.values():
            d = inst.definition
            schemas.append({
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                },
            })
        return schemas

    def discover(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        query_lower = query.lower()
        scores = []
        for name, inst in self._instances.items():
            d = inst.definition
            searchable = f"{name} {d.description}".lower()
            query_words = set(query_lower.split())
            searchable_words = set(searchable.split())
            overlap = len(query_words & searchable_words)
            scores.append((name, float(overlap)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def clear(self) -> None:
        self._registry.clear()
        self._instances.clear()


def tool_register(cls: Type[BaseTool]) -> Type[BaseTool]:
    return ToolRegistry.get_instance().register(cls)