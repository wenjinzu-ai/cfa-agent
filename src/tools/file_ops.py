from __future__ import annotations

import os
from pathlib import Path

from src.models.tool import ToolDefinition, ToolPermission, ToolResult
from src.tools.base import BaseTool
from src.tools.registry import tool_register


def _get_workspace_dir() -> str:
    return os.environ.get("CFA_WORKSPACE_DIR", "./workspace")


def _is_safe_path(file_path: str, safe_dir: str) -> bool:
    path = Path(file_path).resolve()
    safe = Path(safe_dir).resolve()
    try:
        path.relative_to(safe)
        return True
    except ValueError:
        return False


@tool_register
class FileReadTool(BaseTool):
    definition = ToolDefinition(
        name="file_read",
        version="1.0.0",
        description="读取文件内容",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "max_lines": {"type": "integer", "default": 200},
            },
            "required": ["file_path"],
        },
        permissions=[ToolPermission.FILE_READ],
        timeout_seconds=10,
    )

    async def execute(self, file_path: str, max_lines: int = 200) -> ToolResult:
        safe_dir = _get_workspace_dir()
        if not _is_safe_path(file_path, safe_dir):
            return ToolResult(success=False, error=f"路径不在允许的工作目录内: {Path(safe_dir).resolve()}")
        path = Path(file_path).resolve()
        if not path.exists():
            return ToolResult(success=False, error="文件不存在")
        lines = path.read_text(encoding="utf-8").splitlines()[:max_lines]
        return ToolResult(
            success=True, data={"content": "\n".join(lines), "line_count": len(lines)}
        )


@tool_register
class FileWriteTool(BaseTool):
    definition = ToolDefinition(
        name="file_write",
        version="1.0.0",
        description="写入文件内容",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "default": "overwrite",
                },
            },
            "required": ["file_path", "content"],
        },
        permissions=[ToolPermission.FILE_WRITE],
        timeout_seconds=10,
    )

    async def execute(
        self, file_path: str, content: str, mode: str = "overwrite"
    ) -> ToolResult:
        safe_dir = _get_workspace_dir()
        if not _is_safe_path(file_path, safe_dir):
            return ToolResult(success=False, error=f"路径不在允许的工作目录内: {Path(safe_dir).resolve()}")
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with path.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content, encoding="utf-8")
        return ToolResult(success=True, data={"bytes_written": len(content.encode())})