"""BaseTool 和 ToolRegistry 测试"""
from __future__ import annotations

import pytest

from src.tools.base import BaseTool
from src.tools.registry import ToolRegistry
from src.common.types import ToolSource, ToolStatus


class MockTool(BaseTool):
    """Mock 工具用于测试"""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                }
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs):
        return {"result": f"Executed with query: {kwargs.get('query', '')}"}


class FailingTool(BaseTool):
    """失败工具用于测试"""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that always fails"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise RuntimeError("Tool execution failed")


class TestBaseTool:
    """BaseTool 抽象类测试"""

    def test_tool_properties(self):
        """测试工具属性"""
        tool = MockTool()
        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert tool.source == ToolSource.BUILTIN
        assert tool.status == ToolStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试工具执行"""
        tool = MockTool()
        result = await tool.execute(query="test")
        assert result["result"] == "Executed with query: test"

    @pytest.mark.asyncio
    async def test_safe_execute_success(self):
        """测试安全执行 - 成功"""
        tool = MockTool()
        result = await tool.safe_execute(query="test")
        assert result["status"] == "success"
        assert result["tool_name"] == "mock_tool"

    @pytest.mark.asyncio
    async def test_safe_execute_error(self):
        """测试安全执行 - 失败"""
        tool = FailingTool()
        result = await tool.safe_execute()
        assert result["status"] == "error"
        assert "failed" in result["error"]

    def test_to_openai_schema(self):
        """测试 OpenAI Schema 生成"""
        tool = MockTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert schema["function"]["description"] == "A mock tool for testing"
        assert "properties" in schema["function"]["parameters"]
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_is_available(self):
        """测试工具可用性"""
        tool = MockTool()
        assert tool.is_available()

    def test_to_dict(self):
        """测试序列化"""
        tool = MockTool()
        d = tool.to_dict()
        assert d["name"] == "mock_tool"
        assert d["source"] == "builtin"
        assert d["status"] == "active"

    def test_usage_count(self):
        """测试使用次数"""
        tool = MockTool()
        assert tool.usage_count == 0


class TestToolRegistry:
    """ToolRegistry 注册中心测试"""

    def test_register_and_get(self):
        """测试注册和获取"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        retrieved = registry.get("mock_tool")
        assert retrieved is tool

    def test_unregister(self):
        """测试注销"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        registry.unregister("mock_tool")
        assert registry.size == 0

    def test_get_openai_schemas(self):
        """测试获取 OpenAI Schema 列表"""
        registry = ToolRegistry()
        registry.register(MockTool())
        schemas = registry.get_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "mock_tool"

    def test_search_tools(self):
        """测试关键词搜索"""
        registry = ToolRegistry()
        registry.register(MockTool())
        results = registry.search_tools("mock")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """测试通过注册表执行工具"""
        registry = ToolRegistry()
        registry.register(MockTool())
        result = await registry.execute_tool("mock_tool", query="hello")
        assert result["status"] == "success"

    def test_get_active_tools(self):
        """测试获取活跃工具"""
        registry = ToolRegistry()
        registry.register(MockTool())
        active = registry.get_active_tools()
        assert len(active) == 1