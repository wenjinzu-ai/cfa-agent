"""CFA-Agent ToolRegistry 注册中心

统一管理内置工具 + MCP 工具的注册、发现和调度
"""
from __future__ import annotations


from src.tools.base import BaseTool
from src.common.types import ToolSource
from src.common.exceptions import ToolNotFoundError


class ToolRegistry:
    """工具注册中心

    职责：
    - 管理工具的注册与注销
    - 按名称查询工具
    - 提供工具发现机制
    - 生成 OpenAI Function Calling Schema 列表
    - 对上层透明化工具来源差异（builtin / mcp）
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具"""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        del self._tools[name]

    def get(self, name: str) -> BaseTool:
        """获取工具"""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return self._tools[name]

    def get_active_tools(self) -> list[BaseTool]:
        """获取所有活跃工具"""
        return [t for t in self._tools.values() if t.is_available()]

    def get_tools_by_source(self, source: ToolSource) -> list[BaseTool]:
        """按来源获取工具"""
        return [t for t in self._tools.values() if t.source == source]

    def get_openai_schemas(self) -> list[dict]:
        """获取所有活跃工具的 OpenAI Function Calling Schema 列表

        用于 ChatModel.bind_tools() 调用
        """
        return [t.to_openai_schema() for t in self.get_active_tools()]

    def search_tools(self, query: str) -> list[BaseTool]:
        """关键词搜索工具

        在工具名称和描述中搜索匹配的工具
        """
        query_lower = query.lower()
        results = []
        for tool in self.get_active_tools():
            if query_lower in tool.name.lower() or query_lower in tool.description.lower():
                results.append(tool)
        return results

    async def execute_tool(self, name: str, **kwargs) -> dict:
        """执行工具

        Args:
            name: 工具名称
            **kwargs: 工具参数

        Returns:
            dict: 执行结果
        """
        tool = self.get(name)
        if not tool.is_available():
            return {
                "tool_name": name,
                "status": "error",
                "error": f"Tool '{name}' is not available (status: {tool.status.value})",
            }
        return await tool.safe_execute(**kwargs)

    def list_all(self) -> list[BaseTool]:
        """获取所有工具"""
        return list(self._tools.values())

    @property
    def size(self) -> int:
        """已注册工具数量"""
        return len(self._tools)


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表（单例模式）"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry