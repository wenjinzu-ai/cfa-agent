---
name: cfa-ops
description: Use when user asks about CFA-Agent system operations, checking agent status, querying task history, viewing logs, or managing the system itself
triggers:
  - "系统状态"
  - "agent状态"
  - "任务历史"
  - "查看日志"
  - "cfa"
---

# CFA-Agent 运维操作手册

当用户询问 CFA-Agent 系统自身相关问题时，按以下指引操作：

## 查询 Agent 状态
- 使用 `db_query` 工具: `SELECT id, name, role, status FROM agents`
- 或调用 `/api/agents` 接口

## 查询任务历史
- 使用 `db_query` 工具: `SELECT id, description, status, assigned_agent_id, created_at FROM tasks ORDER BY created_at DESC LIMIT 10`
- 按状态过滤: `WHERE status='running'` 或 `WHERE status='completed'`

## 查询会话记录
- 使用 `db_query` 工具: `SELECT id, summary, status, last_activity_at FROM sessions ORDER BY last_activity_at DESC LIMIT 10`

## 查看工具执行日志
- 使用 `db_query` 工具: `SELECT tool_name, status, duration_ms, error_message, created_at FROM tool_executions ORDER BY created_at DESC LIMIT 20`
- 查看失败的工具调用: `WHERE status='error'`

## 查看系统配置
- 集群配置: `SELECT key, value FROM cluster_config`
- Agent 工具绑定: `SELECT agent_id, tool_name, tool_source FROM agent_tool_bindings`

## 常见运维操作
- 清理旧会话: `DELETE FROM sessions WHERE last_activity_at < date('now', '-30 day')`
- 重置 Agent 状态: `UPDATE agents SET status='idle' WHERE status='busy'`