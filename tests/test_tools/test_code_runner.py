import pytest

from src.models.tool import ToolPermission, ToolResult
from src.tools.code_runner import CodeRunnerTool
from src.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


class TestCodeRunnerToolDefinition:
    def test_definition_name(self):
        tool = CodeRunnerTool()
        assert tool.definition.name == "code_runner"

    def test_definition_permissions(self):
        tool = CodeRunnerTool()
        assert ToolPermission.CODE_EXEC in tool.definition.permissions

    def test_definition_timeout(self):
        tool = CodeRunnerTool()
        assert tool.definition.timeout_seconds == 35

    @pytest.mark.asyncio
    async def test_validate_params_valid(self):
        tool = CodeRunnerTool()
        valid, err = await tool.validate_params({"code": "print('hello')"})
        assert valid is True

    @pytest.mark.asyncio
    async def test_validate_params_missing_code(self):
        tool = CodeRunnerTool()
        valid, err = await tool.validate_params({})
        assert valid is False


class TestCodeRunnerToolExecute:
    @pytest.mark.asyncio
    async def test_execute_simple_code(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="print('hello world')")
        assert result.success is True
        assert "hello world" in result.data["output"]

    @pytest.mark.asyncio
    async def test_execute_code_with_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="raise ValueError('test error')")
        assert result.success is False
        assert result.error is not None
        assert "test error" in result.error

    @pytest.mark.asyncio
    async def test_execute_code_with_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="x = 2 + 3\nprint(x)")
        assert result.success is True
        assert "5" in result.data["output"]

    @pytest.mark.asyncio
    async def test_execute_code_timeout(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="import time; time.sleep(60)", timeout=1)
        assert result.success is False
        assert "超时" in result.error

    @pytest.mark.asyncio
    async def test_execute_code_captures_stdout(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="for i in range(3): print(f'line {i}')")
        assert result.success is True
        assert "line 0" in result.data["output"]
        assert "line 1" in result.data["output"]
        assert "line 2" in result.data["output"]

    @pytest.mark.asyncio
    async def test_execute_code_syntax_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = CodeRunnerTool()
        result = await tool.execute(code="print('unclosed string")
        assert result.success is False
        assert result.error is not None