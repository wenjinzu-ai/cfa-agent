import pytest

from src.models.tool import ToolDefinition, ToolPermission, ToolResult
from src.tools.base import BaseTool
from src.tools.registry import ToolRegistry, tool_register


class MockTool(BaseTool):
    definition = ToolDefinition(
        name="mock_tool",
        version="1.0.0",
        description="A mock tool for testing",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "test input"},
            },
            "required": ["input"],
        },
        permissions=[ToolPermission.FILE_READ],
        timeout_seconds=10,
    )

    async def execute(self, input: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"echo": input})


class AnotherMockTool(BaseTool):
    definition = ToolDefinition(
        name="another_tool",
        version="2.0.0",
        description="Another mock tool for search testing",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        permissions=[ToolPermission.NETWORK],
        timeout_seconds=5,
    )

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"result": "ok"})


@pytest.fixture(autouse=True)
def reset_registry():
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


class TestToolRegistrySingleton:
    def test_get_instance_returns_same_object(self):
        a = ToolRegistry.get_instance()
        b = ToolRegistry.get_instance()
        assert a is b

    def test_get_instance_creates_instance(self):
        instance = ToolRegistry.get_instance()
        assert isinstance(instance, ToolRegistry)


class TestToolRegistryRegister:
    def test_register_tool(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        assert reg.get("mock_tool") is not None

    def test_register_creates_instance(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        tool = reg.get("mock_tool")
        assert isinstance(tool, MockTool)

    def test_register_returns_class(self):
        reg = ToolRegistry.get_instance()
        result = reg.register(MockTool)
        assert result is MockTool

    def test_tool_register_decorator(self):
        @tool_register
        class DecoratedTool(BaseTool):
            definition = ToolDefinition(
                name="decorated_tool",
                version="1.0.0",
                description="Decorated tool",
                parameters={"type": "object", "properties": {}, "required": []},
            )

            async def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True)

        reg = ToolRegistry.get_instance()
        assert reg.get("decorated_tool") is not None

    def test_register_multiple_tools(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        assert reg.get("mock_tool") is not None
        assert reg.get("another_tool") is not None

    def test_register_duplicate_name_warns(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(MockTool)
        assert reg.get("mock_tool") is not None


class TestToolRegistryGet:
    def test_get_existing_tool(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        tool = reg.get("mock_tool")
        assert tool is not None
        assert tool.definition.name == "mock_tool"

    def test_get_nonexistent_tool(self):
        reg = ToolRegistry.get_instance()
        assert reg.get("nonexistent") is None

    def test_get_definition(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        defn = reg.get_definition("mock_tool")
        assert defn is not None
        assert defn.name == "mock_tool"
        assert defn.version == "1.0.0"

    def test_get_definition_nonexistent(self):
        reg = ToolRegistry.get_instance()
        assert reg.get_definition("nonexistent") is None


class TestToolRegistryList:
    def test_list_tools(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        tools = reg.list_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "mock_tool" in names
        assert "another_tool" in names

    def test_list_tools_empty(self):
        reg = ToolRegistry.get_instance()
        tools = reg.list_tools()
        assert tools == []

    def test_list_schemas_for_llm(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        schemas = reg.list_schemas_for_llm()
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert "parameters" in schema["function"]


class TestToolRegistryDiscover:
    def test_discover_by_keyword(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        results = reg.discover("mock", top_k=3)
        assert len(results) > 0
        assert results[0][0] == "mock_tool"

    def test_discover_by_description(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        results = reg.discover("search", top_k=3)
        assert len(results) > 0
        assert results[0][0] == "another_tool"

    def test_discover_top_k(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        results = reg.discover("tool", top_k=1)
        assert len(results) == 1

    def test_discover_no_match(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        results = reg.discover("xyz_nonexistent", top_k=3)
        assert all(score == 0.0 for _, score in results)


class TestToolRegistryClear:
    def test_clear_removes_all(self):
        reg = ToolRegistry.get_instance()
        reg.register(MockTool)
        reg.register(AnotherMockTool)
        assert len(reg.list_tools()) == 2
        reg.clear()
        assert len(reg.list_tools()) == 0
        assert reg.get("mock_tool") is None