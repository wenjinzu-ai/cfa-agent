"""CFA-Agent 数据库工具

安全策略：增删改查，禁止结构变更
- 允许 SELECT / INSERT / UPDATE / DELETE 数据操作
- 禁止 DROP / ALTER / CREATE / ATTACH / PRAGMA 等结构变更
- 禁止多语句执行，防止注入
- 查询结果行数限制（默认 100 行）
- 超时控制
- 自动注入数据库路径，Agent 无需知道文件位置
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from pydantic import Field

from src.tools.base import BaseTool

logger = logging.getLogger("cfa-agent.tools.db_query")

_FORBIDDEN_PATTERNS = [
    (r"\bDROP\b", "DROP 禁止使用，不允许修改表结构"),
    (r"\bALTER\b", "ALTER 禁止使用，不允许修改表结构"),
    (r"\bCREATE\b", "CREATE 禁止使用，不允许修改表结构"),
    (r"\bATTACH\b", "ATTACH 禁止使用"),
    (r"\bDETACH\b", "DETACH 禁止使用"),
    (r"\bPRAGMA\b", "PRAGMA 禁止使用"),
    (r"\bVACUUM\b", "VACUUM 禁止使用"),
    (r";", "禁止多语句执行，只允许单条 SQL"),
    (r"--", "禁止 SQL 注释"),
    (r"/\*", "禁止 SQL 注释"),
]

_TABLE_COMMENTS = {
    "tasks": "任务记录（id, session_id, description, status, assigned_agent_id, result, created_at, completed_at）",
    "sessions": "会话记录（id, status, summary, last_activity_at, created_at）",
    "agents": "智能体注册（id, name, role, status, config, last_heartbeat, created_at）",
    "tool_executions": "工具执行日志（id, tool_name, agent_id, task_id, status, duration_ms, error_message, created_at）",
    "memories": "记忆存储（id, agent_id, memory_type, content, importance, access_count, created_at）",
    "react_steps": "ReAct 步骤轨迹（id, task_id, agent_id, step_index, thought, action, observation, status, created_at）",
    "events": "事件记录（id, event_type, agent_id, task_id, payload, created_at）",
    "audit_log": "审计日志（id, agent_id, action, details, created_at）",
    "mcp_servers": "MCP 服务器配置（id, name, transport, config, status, tools_count, last_connected_at）",
    "mcp_tools": "MCP 工具缓存（id, server_id, tool_name, tool_schema, is_available）",
    "tools": "工具注册表（id, name, version, status, usage_count, created_at）",
    "agent_tool_bindings": "智能体工具绑定（agent_id, tool_name, tool_source, proficiency）",
    "cluster_config": "集群配置（key, value, updated_at）",
}

_ALLOWED_PREFIXES = ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")


class DBQuery(BaseTool):
    """数据库增删改查工具

    安全策略：
    - 允许 SELECT / INSERT / UPDATE / DELETE 数据操作
    - 禁止 DROP / ALTER / CREATE 等结构变更
    - 禁止多语句执行
    - 查询结果行数限制
    - 超时控制
    """

    name: str = "db_query"
    description: str = (
        "Execute SQL on the CFA-Agent database. "
        "Allowed: SELECT, INSERT, UPDATE, DELETE. "
        "Forbidden: DROP, ALTER, CREATE, ATTACH, PRAGMA (structure changes). "
        "Returns results as a list of dictionaries for SELECT, or affected row count for INSERT/UPDATE/DELETE. "
        "Available tables: tasks, sessions, agents, tool_executions, memories, react_steps, events, audit_log, mcp_servers, mcp_tools, tools, agent_tool_bindings, cluster_config."
    )
    max_rows: int = Field(default=100, description="Maximum number of rows to return for SELECT")
    timeout: float = Field(default=10.0, description="Query timeout in seconds")

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "SQL statement to execute. Allowed: SELECT, INSERT, UPDATE, DELETE. "
                        "Examples: 'SELECT * FROM tasks WHERE status=\"running\"', "
                        "'UPDATE tasks SET status=\"completed\" WHERE id=\"xxx\"', "
                        "'DELETE FROM events WHERE created_at < \"2026-01-01\"', "
                        "'INSERT INTO agents (id, name, role, status) VALUES (\"a1\", \"test\", \"worker\", \"idle\")'"
                    ),
                },
                "max_rows": {
                    "type": "integer",
                    "description": f"Maximum rows to return for SELECT (default: {self.max_rows})",
                    "default": self.max_rows,
                },
            },
            "required": ["sql"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        sql = kwargs.get("sql", "").strip()
        max_rows = kwargs.get("max_rows", self.max_rows)

        if not sql:
            return {"status": "error", "error": "No SQL query provided"}

        validation_error = self._validate_sql(sql)
        if validation_error:
            return {"status": "blocked", "error": validation_error}

        try:
            result = await asyncio.wait_for(
                self._execute_sql(sql, max_rows),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            return {"status": "timeout", "error": f"Query timed out after {self.timeout}s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _validate_sql(self, sql: str) -> str | None:
        sql_upper = sql.upper().strip()

        if not any(sql_upper.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
            return f"只允许 {'/'.join(_ALLOWED_PREFIXES)} 操作，语句必须以这些关键字开头"

        for pattern, reason in _FORBIDDEN_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return f"SQL 安全检查不通过: {reason}"

        return None

    async def _execute_sql(self, sql: str, max_rows: int) -> dict[str, Any]:
        import sqlite3

        from src.common.settings import get_config

        db_path = str(get_config().db_absolute_path)
        sql_upper = sql.upper().strip()
        is_read = sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")

        try:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if is_read:
                limited_sql = f"{sql.rstrip(';')} LIMIT {max_rows}"
                if "LIMIT" in sql.upper():
                    limited_sql = sql.rstrip(";")
                cursor.execute(limited_sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                result_rows = [dict(zip(columns, row)) for row in rows]
                conn.close()
                return {
                    "status": "success",
                    "action": "select",
                    "columns": columns,
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "truncated": len(result_rows) >= max_rows,
                    "tables": _TABLE_COMMENTS,
                }
            else:
                cursor.execute(sql.rstrip(";"))
                affected = cursor.rowcount
                conn.commit()
                conn.close()
                return {
                    "status": "success",
                    "action": sql_upper.split()[0].lower(),
                    "affected_rows": affected,
                    "tables": _TABLE_COMMENTS,
                }

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if "no such table" in error_msg:
                return {
                    "status": "error",
                    "error": f"表不存在: {error_msg}",
                    "available_tables": list(_TABLE_COMMENTS.keys()),
                }
            return {"status": "error", "error": error_msg}
        except Exception as e:
            return {"status": "error", "error": str(e)}