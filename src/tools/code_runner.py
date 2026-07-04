from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models.tool import ToolDefinition, ToolPermission, ToolResult
from src.tools.base import BaseTool
from src.tools.registry import tool_register


@tool_register
class CodeRunnerTool(BaseTool):
    definition = ToolDefinition(
        name="code_runner",
        version="1.0.0",
        description="执行 Python 代码片段（沙箱环境）",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["code"],
        },
        permissions=[ToolPermission.CODE_EXEC],
        timeout_seconds=35,
    )

    async def execute(self, code: str, timeout: int = 30) -> ToolResult:
        dangerous_keywords = [
            "import os", "import subprocess", "import sys",
            "__import__", "eval(", "exec(", "compile(",
            "open(", "shutil.", "pathlib.Path",
        ]
        code_lower = code.lower()
        for kw in dangerous_keywords:
            if kw.lower() in code_lower:
                return ToolResult(
                    success=False,
                    error=f"代码包含受限操作: {kw}，不允许执行",
                )

        tmp_dir = Path(tempfile.mkdtemp(prefix="cfa_workspace_"))
        with tempfile.NamedTemporaryFile(
            suffix=".py",
            mode="w",
            delete=False,
            prefix="cfa_exec_",
            dir=str(tmp_dir),
        ) as f:
            f.write(code)
            tmp_file = f.name

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                tmp_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(tmp_dir),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")[:5000]
            errors = stderr.decode("utf-8", errors="replace")[:2000]
            return ToolResult(
                success=proc.returncode == 0,
                data={"output": output},
                error=errors if errors else None,
            )
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return ToolResult(success=False, error=f"代码执行超时 ({timeout}s)")
        finally:
            Path(tmp_file).unlink(missing_ok=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)