"""CFA-Agent 文件操作工具

安全策略：
- 沙箱目录：默认 ./data/workspace，禁止访问项目根目录和敏感文件
- 路径穿越防护：resolve 后必须以 base_dir 为前缀（大小写不敏感）
- 敏感文件屏蔽：禁止读写 .env/.git/配置文件等
- 删除保护：禁止删除 workspace 根目录
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from pydantic import Field

from src.tools.base import BaseTool

logger = logging.getLogger("cfa-agent.tools.file_ops")

_BLOCKED_NAMES = frozenset({
    ".env", ".env.local", ".env.production", ".env.development",
    ".gitignore", ".git", ".htaccess", ".htpasswd",
    "id_rsa", "id_ed25519", "id_ecdsa",
    ".ssh", ".gnupg", ".aws",
})

_BLOCKED_EXTENSIONS = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".jks",
})


class FileOps(BaseTool):
    """文件操作工具

    在沙箱目录内提供安全的文件读写、列表、删除等操作
    """

    name: str = "file_ops"
    description: str = (
        "Read, write, list, and delete files in the sandboxed workspace directory. "
        "Cannot access files outside the workspace or sensitive system files."
    )
    base_dir: str = Field(default="./data/workspace", description="Sandbox base directory")
    max_file_size: int = Field(default=10485760, description="Max file size in bytes (10MB)")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Operation: read, write, list, delete, exists, mkdir, copy, move",
                    "enum": ["read", "write", "list", "delete", "exists", "mkdir", "copy", "move"],
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path (relative to workspace)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write operation)",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path (for copy/move operations)",
                },
            },
            "required": ["operation", "path"],
        }

    def _ensure_base_dir(self) -> Path:
        base = Path(self.base_dir)
        if not base.is_absolute():
            base = Path.cwd() / base
        base = base.resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _resolve_path(self, path: str) -> Path | None:
        base = self._ensure_base_dir()
        resolved = (base / path).resolve()

        try:
            resolved.relative_to(base)
        except ValueError:
            logger.warning(f"Path traversal blocked: {path} -> {resolved}")
            return None

        if resolved.name in _BLOCKED_NAMES or resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
            logger.warning(f"Sensitive file blocked: {resolved.name}")
            return None

        for parent in resolved.parents:
            if parent.name in _BLOCKED_NAMES:
                logger.warning(f"Sensitive directory blocked: {parent.name}")
                return None

        return resolved

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        operation = kwargs.get("operation", "")
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        destination = kwargs.get("destination", "")

        full_path = self._resolve_path(path)
        if not full_path:
            return {"operation": operation, "path": path, "error": "Path not allowed or outside workspace", "status": "error"}

        try:
            if operation == "read":
                return await self._read(full_path)
            elif operation == "write":
                return await self._write(full_path, content)
            elif operation == "list":
                return await self._list(full_path)
            elif operation == "delete":
                return await self._delete(full_path)
            elif operation == "exists":
                return await self._exists(full_path)
            elif operation == "mkdir":
                return await self._mkdir(full_path)
            elif operation == "copy":
                return await self._copy(full_path, destination)
            elif operation == "move":
                return await self._move(full_path, destination)
            else:
                return {"operation": operation, "error": f"Unknown operation: {operation}", "status": "error"}
        except Exception as e:
            return {"operation": operation, "path": path, "error": str(e), "status": "error"}

    async def _read(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"operation": "read", "path": str(path), "error": "File not found", "status": "error"}
        if not path.is_file():
            return {"operation": "read", "path": str(path), "error": "Not a file", "status": "error"}
        if path.stat().st_size > self.max_file_size:
            return {"operation": "read", "path": str(path), "error": "File too large", "status": "error"}
        content = path.read_text(encoding="utf-8")
        return {"operation": "read", "path": str(path), "content": content, "size": len(content), "status": "success"}

    async def _write(self, path: Path, content: str) -> dict[str, Any]:
        if len(content) > self.max_file_size:
            return {"operation": "write", "path": str(path), "error": "Content too large", "status": "error"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"operation": "write", "path": str(path), "size": len(content), "status": "success"}

    async def _list(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"operation": "list", "path": str(path), "error": "Directory not found", "status": "error"}
        if not path.is_dir():
            return {"operation": "list", "path": str(path), "error": "Not a directory", "status": "error"}
        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
        return {"operation": "list", "path": str(path), "items": items, "count": len(items), "status": "success"}

    async def _delete(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"operation": "delete", "path": str(path), "error": "Not found", "status": "error"}
        base = self._ensure_base_dir()
        if path == base:
            return {"operation": "delete", "path": str(path), "error": "Cannot delete workspace root", "status": "error"}
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"operation": "delete", "path": str(path), "status": "success"}

    async def _exists(self, path: Path) -> dict[str, Any]:
        return {"operation": "exists", "path": str(path), "exists": path.exists(), "status": "success"}

    async def _mkdir(self, path: Path) -> dict[str, Any]:
        path.mkdir(parents=True, exist_ok=True)
        return {"operation": "mkdir", "path": str(path), "status": "success"}

    async def _copy(self, src: Path, dst: str) -> dict[str, Any]:
        dst_path = self._resolve_path(dst)
        if not dst_path:
            return {"operation": "copy", "path": str(src), "error": "Invalid destination", "status": "error"}
        if src.is_dir():
            shutil.copytree(src, dst_path)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_path)
        return {"operation": "copy", "from": str(src), "to": str(dst_path), "status": "success"}

    async def _move(self, src: Path, dst: str) -> dict[str, Any]:
        dst_path = self._resolve_path(dst)
        if not dst_path:
            return {"operation": "move", "path": str(src), "error": "Invalid destination", "status": "error"}
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_path))
        return {"operation": "move", "from": str(src), "to": str(dst_path), "status": "success"}