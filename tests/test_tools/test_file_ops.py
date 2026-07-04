import pytest
from pathlib import Path

from src.models.tool import ToolPermission, ToolResult
from src.tools.file_ops import FileReadTool, FileWriteTool, _is_safe_path
from src.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws.resolve())


class TestIsSafePath:
    def test_safe_path(self, workspace):
        assert _is_safe_path(str(Path(workspace) / "test.txt"), workspace) is True

    def test_unsafe_path(self, workspace):
        assert _is_safe_path("/etc/passwd", workspace) is False

    def test_prefix_trick_blocked(self, workspace):
        trick_path = str(Path(workspace).parent / (Path(workspace).name + "_evil") / "test.txt")
        assert _is_safe_path(trick_path, workspace) is False

    def test_nested_safe_path(self, workspace):
        assert _is_safe_path(str(Path(workspace) / "sub" / "dir" / "file.txt"), workspace) is True


class TestFileReadToolDefinition:
    def test_definition_name(self):
        tool = FileReadTool()
        assert tool.definition.name == "file_read"

    def test_definition_permissions(self):
        tool = FileReadTool()
        assert ToolPermission.FILE_READ in tool.definition.permissions

    @pytest.mark.asyncio
    async def test_validate_params_valid(self):
        tool = FileReadTool()
        valid, err = await tool.validate_params({"file_path": "/some/path"})
        assert valid is True

    @pytest.mark.asyncio
    async def test_validate_params_missing_path(self):
        tool = FileReadTool()
        valid, err = await tool.validate_params({})
        assert valid is False


class TestFileReadToolExecute:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        test_file = Path(workspace) / "test.txt"
        test_file.write_text("hello\nworld", encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute(file_path=str(test_file))
        assert result.success is True
        assert "hello" in result.data["content"]
        assert result.data["line_count"] == 2

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        tool = FileReadTool()
        result = await tool.execute(file_path=str(Path(workspace) / "nonexistent.txt"))
        assert result.success is False
        assert "不存在" in result.error

    @pytest.mark.asyncio
    async def test_read_outside_workspace(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        tool = FileReadTool()
        result = await tool.execute(file_path="/etc/passwd")
        assert result.success is False
        assert "不在允许的工作目录内" in result.error

    @pytest.mark.asyncio
    async def test_read_with_max_lines(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        test_file = Path(workspace) / "multiline.txt"
        test_file.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")

        tool = FileReadTool()
        result = await tool.execute(file_path=str(test_file), max_lines=10)
        assert result.success is True
        assert result.data["line_count"] == 10


class TestFileWriteToolDefinition:
    def test_definition_name(self):
        tool = FileWriteTool()
        assert tool.definition.name == "file_write"

    def test_definition_permissions(self):
        tool = FileWriteTool()
        assert ToolPermission.FILE_WRITE in tool.definition.permissions

    @pytest.mark.asyncio
    async def test_validate_params_valid(self):
        tool = FileWriteTool()
        valid, err = await tool.validate_params({"file_path": "/some/path", "content": "hello"})
        assert valid is True

    @pytest.mark.asyncio
    async def test_validate_params_missing_content(self):
        tool = FileWriteTool()
        valid, err = await tool.validate_params({"file_path": "/some/path"})
        assert valid is False


class TestFileWriteToolExecute:
    @pytest.mark.asyncio
    async def test_write_new_file(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        tool = FileWriteTool()
        result = await tool.execute(
            file_path=str(Path(workspace) / "new.txt"), content="hello world"
        )
        assert result.success is True
        assert result.data["bytes_written"] > 0
        assert (Path(workspace) / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_append_mode(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        test_file = Path(workspace) / "append.txt"
        test_file.write_text("first\n", encoding="utf-8")

        tool = FileWriteTool()
        result = await tool.execute(
            file_path=str(test_file), content="second\n", mode="append"
        )
        assert result.success is True
        content = test_file.read_text()
        assert "first" in content
        assert "second" in content

    @pytest.mark.asyncio
    async def test_write_overwrite_mode(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        test_file = Path(workspace) / "overwrite.txt"
        test_file.write_text("old content", encoding="utf-8")

        tool = FileWriteTool()
        result = await tool.execute(
            file_path=str(test_file), content="new content", mode="overwrite"
        )
        assert result.success is True
        assert test_file.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_write_outside_workspace(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        tool = FileWriteTool()
        result = await tool.execute(file_path="/tmp/evil.txt", content="hack")
        assert result.success is False
        assert "不在允许的工作目录内" in result.error

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, workspace, monkeypatch):
        monkeypatch.setenv("CFA_WORKSPACE_DIR", workspace)
        tool = FileWriteTool()
        result = await tool.execute(
            file_path=str(Path(workspace) / "sub" / "dir" / "file.txt"), content="nested"
        )
        assert result.success is True
        assert (Path(workspace) / "sub" / "dir" / "file.txt").read_text() == "nested"