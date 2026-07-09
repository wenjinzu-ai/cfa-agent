"""CFA-Agent 工具动态加载器

自动发现并加载内置工具和 MCP 工具
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Type

from src.tools.base import BaseTool
from src.tools.registry import get_tool_registry
from src.common.types import ToolSource


class ToolLoader:
    """工具动态加载器

    职责：
    - 自动扫描 src/tools/builtin/ 目录下的工具模块
    - 动态导入并注册工具到 ToolRegistry
    - 支持 MCP 工具的动态加载
    """

    def __init__(self, builtin_dir: str | Path = "src/tools/builtin"):
        self._builtin_dir = Path(builtin_dir)
        self._registry = get_tool_registry()

    async def load_builtin_tools(self) -> list[Type[BaseTool]]:
        """加载所有内置工具

        Returns:
            list[Type[BaseTool]]: 加载的工具类列表
        """
        loaded_tools = []

        if not self._builtin_dir.exists():
            return loaded_tools

        for module_file in self._builtin_dir.glob("*.py"):
            if module_file.name.startswith("_"):
                continue

            tool_class = await self.load_tool_from_module_file(module_file)
            if tool_class:
                loaded_tools.append(tool_class)

        return loaded_tools

    async def load_tool_from_module_file(self, module_file: Path) -> Type[BaseTool] | None:
        """从模块文件加载工具类

        Args:
            module_file: 模块文件路径

        Returns:
            Type[BaseTool] | None: 工具类，加载失败返回 None
        """
        module_name = module_file.stem
        full_module_path = f"src.tools.builtin.{module_name}"

        try:
            module = importlib.import_module(full_module_path)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and obj.__module__ == full_module_path
                ):
                    return obj

        except Exception as e:
            print(f"[ToolLoader] Failed to load tool from {module_file}: {e}")

        return None

    async def load_tool_from_module(self, module_path: str) -> BaseTool | None:
        """从指定模块路径加载工具实例

        Args:
            module_path: 模块路径（如 'src.tools.builtin.web_search'）

        Returns:
            BaseTool | None: 工具实例，加载失败返回 None
        """
        try:
            module = importlib.import_module(module_path)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and obj.__module__ == module_path
                ):
                    return obj()

        except Exception as e:
            print(f"[ToolLoader] Failed to load tool from {module_path}: {e}")

        return None

    async def register_builtin_tools(self) -> int:
        """加载并注册所有内置工具到全局注册表

        Returns:
            int: 注册的工具数量
        """
        count = 0

        tool_classes = await self.load_builtin_tools()
        for tool_class in tool_classes:
            try:
                tool_instance = tool_class()
                self._registry.register(tool_instance)
                count += 1
                print(f"[ToolLoader] Registered builtin tool: {tool_instance.name}")
            except Exception as e:
                print(f"[ToolLoader] Failed to register tool {tool_class.__name__}: {e}")

        return count

    async def load_and_register_specific_tools(self, tool_names: list[str]) -> int:
        """加载并注册指定的工具

        Args:
            tool_names: 工具名称列表（如 ['web_search', 'code_executor']）

        Returns:
            int: 注册的工具数量
        """
        count = 0

        for tool_name in tool_names:
            module_path = f"src.tools.builtin.{tool_name}"
            tool_instance = await self.load_tool_from_module(module_path)

            if tool_instance:
                self._registry.register(tool_instance)
                count += 1

        return count

    def get_loaded_tools(self) -> list[str]:
        """获取已加载的工具名称列表

        Returns:
            list[str]: 工具名称列表
        """
        return [t.name for t in self._registry.list_all()]


async def initialize_builtin_tools() -> int:
    """初始化内置工具（加载并注册到全局注册表）

    Returns:
        int: 注册的工具数量
    """
    loader = ToolLoader()
    return await loader.register_builtin_tools()