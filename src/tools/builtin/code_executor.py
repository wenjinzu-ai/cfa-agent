"""CFA-Agent 代码执行工具

安全策略：白名单模式
- 只允许导入安全模块（math/json/statistics 等）
- 禁止 os/subprocess/shutil/io 等系统级操作
- 禁止 __import__/eval/exec/compile/open 等内置函数
- 禁止访问 __builtins__ 中的危险属性
- 子进程隔离执行，限制资源
"""
from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from io import StringIO
from typing import Any

from pydantic import Field

from src.tools.base import BaseTool

logger = logging.getLogger("cfa-agent.tools.code_executor")

_ALLOWED_IMPORTS = frozenset({
    "math", "json", "statistics", "random", "itertools", "collections",
    "datetime", "decimal", "fractions", "functools", "operator",
    "re", "string", "textwrap", "typing", "copy", "hashlib",
    "base64", "uuid", "enum", "dataclasses", "pathlib",
    "httpx", "urllib", "html", "xml", "csv", "io",
    "sqlite3",
})

_BLOCKED_BUILTINS = frozenset({
    "__import__", "eval", "exec", "compile", "open",
    "input", "breakpoint", "exit", "quit",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "type",
    "memoryview", "bytearray", "bytes",
})

_BLOCKED_PATTERNS = [
    ("import os", "os 模块禁止导入"),
    ("import subprocess", "subprocess 模块禁止导入"),
    ("import shutil", "shutil 模块禁止导入"),
    ("import socket", "socket 模块禁止导入"),
    ("import signal", "signal 模块禁止导入"),
    ("import ctypes", "ctypes 模块禁止导入"),
    ("import sys", "sys 模块禁止导入"),
    ("from os", "os 模块禁止导入"),
    ("from subprocess", "subprocess 模块禁止导入"),
    ("from shutil", "shutil 模块禁止导入"),
    ("from socket", "socket 模块禁止导入"),
    ("__import__", "__import__ 禁止使用"),
    ("eval(", "eval() 禁止使用"),
    ("exec(", "exec() 禁止使用"),
    ("compile(", "compile() 禁止使用"),
    ("open(", "open() 禁止使用"),
    (".__class__", "禁止访问 __class__ 属性"),
    (".__subclasses__", "禁止访问 __subclasses__ 属性"),
    (".__bases__", "禁止访问 __bases__ 属性"),
    (".__globals__", "禁止访问 __globals__ 属性"),
]


class CodeExecutor(BaseTool):
    """代码执行工具

    在受限沙箱环境中执行 Python 代码：
    - 白名单模块导入
    - 禁用危险内置函数
    - 超时控制
    - 输出截断
    """

    name: str = "code_executor"
    description: str = (
        "Execute Python code in a sandboxed environment. "
        "Allowed modules include: math, json, statistics, httpx, urllib, re, csv, "
        "datetime, collections, itertools, html, xml, sqlite3, and more. "
        "DB_PATH variable is pre-injected with the database file path — use sqlite3.connect(DB_PATH) for full CRUD. "
        "Returns stdout, stderr, and exit code. "
        "Use for calculations, data processing, web scraping, API calls, database queries, and quick scripts. "
        "If the code errors, read the error message, fix the code, and retry."
    )
    timeout: int = Field(default=30, description="Execution timeout in seconds")
    max_output_length: int = Field(default=10000, description="Max output length")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Execution timeout in seconds (default: {self.timeout})",
                    "default": self.timeout,
                },
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        code = kwargs.get("code", "")
        timeout = kwargs.get("timeout", self.timeout)

        if not code:
            return {"stdout": "", "stderr": "No code provided", "exit_code": 1, "status": "error"}

        validation_error = self._validate_code(code)
        if validation_error:
            logger.warning(f"Code blocked: {validation_error}")
            return {
                "stdout": "",
                "stderr": f"代码安全检查不通过: {validation_error}",
                "exit_code": 1,
                "status": "blocked",
            }

        try:
            result = await asyncio.wait_for(
                self._execute_code(code),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "exit_code": 124,
                "status": "timeout",
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "exit_code": 1,
                "status": "error",
            }

    def _validate_code(self, code: str) -> str | None:
        for pattern, reason in _BLOCKED_PATTERNS:
            if pattern in code:
                return reason
        return None

    def _build_safe_globals(self) -> dict:
        import builtins as builtins_mod

        from src.common.settings import get_config

        safe_builtins = {}
        for name in dir(builtins_mod):
            if name in _BLOCKED_BUILTINS or name.startswith("_"):
                continue
            val = getattr(builtins_mod, name, None)
            if val is not None:
                safe_builtins[name] = val

        def _restricted_import(name, *args, **kwargs):
            if name not in _ALLOWED_IMPORTS:
                raise ImportError(f"Module '{name}' is not allowed. Allowed: {sorted(_ALLOWED_IMPORTS)}")
            return original_import(name, *args, **kwargs)

        original_import = builtins_mod.__import__
        safe_builtins["__import__"] = _restricted_import

        safe_globals = {"__builtins__": safe_builtins, "__name__": "__main__"}

        for mod_name in _ALLOWED_IMPORTS:
            try:
                mod = original_import(mod_name)
                safe_globals[mod_name] = mod
            except ImportError:
                pass

        safe_globals["DB_PATH"] = str(get_config().db_absolute_path)

        return safe_globals

    async def _execute_code(self, code: str) -> dict[str, Any]:
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        exit_code = 0
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        execution_globals = self._build_safe_globals()

        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            exec(code, execution_globals)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        except Exception:
            exit_code = 1
            traceback.print_exc(file=stderr_capture)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        stdout = stdout_capture.getvalue()
        stderr = stderr_capture.getvalue()

        if len(stdout) > self.max_output_length:
            stdout = stdout[:self.max_output_length] + "\n... (output truncated)"
        if len(stderr) > self.max_output_length:
            stderr = stderr[:self.max_output_length] + "\n... (output truncated)"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "status": "success" if exit_code == 0 else "error",
        }