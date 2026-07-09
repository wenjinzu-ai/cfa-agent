"""CFA-Agent 数据库 Schema 与迁移管理

根据技术方案创建所有核心表结构，管理数据库版本迁移。
"""
from __future__ import annotations

import logging

from src.db.connection import DatabaseConnection

logger = logging.getLogger("cfa-agent.db.schema")


SCHEMA_SQL = """
-- ========================================
-- 智能体管理
-- ========================================

-- 智能体注册信息表
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle', 'busy', 'error', 'sleeping')),
    config TEXT,  -- JSON 格式配置
    performance_metrics TEXT,  -- JSON 格式性能指标
    last_heartbeat TEXT,  -- ISO 8601 时间戳
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(role);

-- 智能体工具绑定表
CREATE TABLE IF NOT EXISTS agent_tool_bindings (
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_source TEXT NOT NULL CHECK(tool_source IN ('builtin', 'mcp')),
    proficiency REAL DEFAULT 0.5 CHECK(proficiency BETWEEN 0 AND 1),
    PRIMARY KEY (agent_id, tool_name),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- ========================================
-- 工具管理
-- ========================================

-- 工具注册表
CREATE TABLE IF NOT EXISTS tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    version TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'deprecated', 'disabled')),
    usage_count INTEGER DEFAULT 0,
    avg_rating REAL CHECK(avg_rating BETWEEN 0 AND 5),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tools_status ON tools(status);
CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(name);

-- 工具执行日志表
CREATE TABLE IF NOT EXISTS tool_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    agent_id TEXT,
    task_id TEXT,
    input_params TEXT,  -- JSON 格式输入参数
    output_result TEXT,  -- JSON 格式输出结果
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
    duration_ms INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tool_executions_tool ON tool_executions(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_executions_agent ON tool_executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_task ON tool_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_status ON tool_executions(status);

-- ========================================
-- MCP 管理
-- ========================================

-- MCP Server 配置表
CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    transport TEXT NOT NULL CHECK(transport IN ('stdio', 'sse', 'streamable-http')),
    config TEXT,  -- JSON 格式连接配置
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK(status IN ('disconnected', 'connecting', 'connected', 'error')),
    tools_count INTEGER DEFAULT 0,
    last_connected_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mcp_servers_status ON mcp_servers(status);

-- MCP 工具缓存表
CREATE TABLE IF NOT EXISTS mcp_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    tool_schema TEXT,  -- JSON 格式工具 Schema
    is_available BOOLEAN DEFAULT 1,
    FOREIGN KEY (server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE,
    UNIQUE (server_id, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_tools_server ON mcp_tools(server_id);

-- ========================================
-- 任务管理
-- ========================================

-- 任务记录表
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    parent_task_id TEXT,
    session_id TEXT,
    conversation_index INTEGER DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'sync' CHECK(mode IN ('sync', 'async')),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'assigned', 'running', 'waiting_user', 'completed', 'failed', 'cancelled')),
    introspection_state TEXT CHECK(introspection_state IN ('sleeping', 'aware', 'thinking', 'acting', 'observing', 'answering', 'reflecting', 'self_correcting', 'alerting')),
    priority INTEGER DEFAULT 0,
    assigned_agent_id TEXT,
    plan TEXT,  -- JSON 格式执行计划
    result TEXT,  -- JSON 格式执行结果
    cached_result TEXT,  -- JSON 格式缓存结果
    result_expires_at TEXT,  -- ISO 8601 时间戳
    waiting_question TEXT,  -- ask_user 时的问题内容
    uploaded_files TEXT,  -- JSON 格式文件列表
    iteration_count INTEGER DEFAULT 0,
    max_iterations INTEGER DEFAULT 20,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_agent_id) REFERENCES agents(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(assigned_agent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

-- ========================================
-- 会话管理
-- ========================================

-- 会话记录表
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived', 'expired')),
    session_history TEXT,  -- JSON 数组格式对话历史
    summary TEXT,
    last_activity_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity_at);

-- ========================================
-- 记忆系统
-- ========================================

-- 记忆存储表
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    memory_type TEXT NOT NULL CHECK(memory_type IN ('episodic', 'semantic', 'procedural')),
    content TEXT NOT NULL,
    embedding BLOB,  -- 向量嵌入
    importance REAL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);

-- FTS5 全文搜索索引
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='id'
);

-- FTS5 同步触发器
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

-- ReAct 步骤轨迹表
CREATE TABLE IF NOT EXISTS react_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT,
    step_index INTEGER NOT NULL,
    thought TEXT,
    action TEXT,  -- JSON 格式工具调用
    observation TEXT,
    duration_ms INTEGER,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_react_steps_task ON react_steps(task_id);
CREATE INDEX IF NOT EXISTS idx_react_steps_agent ON react_steps(agent_id);

-- ========================================
-- 事件与审计
-- ========================================

-- 事件记录表
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    agent_id TEXT,
    task_id TEXT,
    payload TEXT,  -- JSON 格式事件数据
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    action TEXT NOT NULL,
    details TEXT,  -- JSON 格式操作详情
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_log_agent ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

-- ========================================
-- 集群配置
-- ========================================

-- 集群配置表
CREATE TABLE IF NOT EXISTS cluster_config (
    key TEXT PRIMARY KEY,
    value TEXT,  -- JSON 格式配置值
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


async def init_database(db: DatabaseConnection) -> None:
    """初始化数据库 Schema

    Args:
        db: 数据库连接实例
    """
    await db.executescript(SCHEMA_SQL)
    await db.commit()


async def check_database_schema(db: DatabaseConnection) -> bool:
    """检查数据库 Schema 是否已初始化

    Args:
        db: 数据库连接实例

    Returns:
        bool: 是否已初始化
    """
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
    )
    row = await cursor.fetchone()
    return row is not None


class MigrationManager:
    """Schema 迁移管理器

    管理数据库版本迁移，支持增量迁移脚本。
    """

    _current_version: int = 1

    def __init__(self, db):
        self._db = db

    async def get_current_version(self) -> int:
        """获取当前数据库版本"""
        from src.db.connection import DatabaseConnection

        if isinstance(self._db, DatabaseConnection):
            cursor = await self._db.execute(
                "SELECT value FROM cluster_config WHERE key = 'schema_version'"
            )
            row = await cursor.fetchone()
            if row:
                return int(row[0])
        return 0

    async def set_version(self, version: int) -> None:
        """设置数据库版本"""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO cluster_config (key, value)
            VALUES ('schema_version', ?)
            """,
            (str(version),),
        )
        await self._db.commit()

    async def run_migrations(self) -> int:
        """运行待执行的迁移

        Returns:
            int: 迁移后的版本号
        """
        current = await self.get_current_version()
        if current < self._current_version:
            logger.info("Running migration: %d → %d", current, self._current_version)
            await self.set_version(self._current_version)
        return self._current_version