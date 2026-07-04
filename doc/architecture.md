# CFA-Agent 自主决策智能体架构设计

## 1. 系统总览

```
+-------------------------------------------------------------+
|                      CFA-Agent System                        |
|-------------------------------------------------------------|
|                                                              |
|  +-----------+    +--------------+    +------------------+   |
|  |  用户接口  |--->|  Agent Core  |--->|    执行输出层     |   |
|  |  (Input)  |<---|  (决策中枢)   |<---|  (Action Output) |   |
|  +-----------+    +------+-------+    +------------------+   |
|                          |                                   |
|          +---------------+---------------+                  |
|          v               v               v                  |
|  +----------+    +------------+   +------------+            |
|  |  规划模块  |    |  记忆模块   |   |  工具模块   |            |
|  | (Planner) |    | (Memory)   |   |  (Tools)   |            |
|  +----------+    +------------+   +------------+            |
|                                                              |
+-------------------------------------------------------------+
```

---

## 2. 核心模块设计

### 2.1 Agent Core - 决策中枢

Agent Core 是整个系统的"大脑"，负责协调各模块完成自主决策。

```
+---------------------------------------------+
|                Agent Core                     |
|                                               |
|  +-------------+  +-----------------------+  |
|  |   感知引擎   |  |      推理引擎         |  |
|  | (Perception)|  |    (Reasoning)        |  |
|  |             |  |                       |  |
|  | - 输入解析  |  | - Chain-of-Thought    |  |
|  | - 意图识别  |  | - ReAct 推理          |  |
|  | - 上下文提取|  | - 反思与自校正        |  |
|  +------+------++  +-----------+-----------+  |
|         |                     |               |
|         v                     v               |
|  +-----------------------------------------+  |
|  |            决策调度器                     |  |
|  |         (Decision Dispatcher)            |  |
|  |                                         |  |
|  |  - 路由：选择下一步行动类型              |  |
|  |  - 优先级：处理冲突与抢占                |  |
|  |  - 熔断：异常时降级或终止                |  |
|  +-----------------------------------------+  |
|                                               |
+---------------------------------------------+
```

**核心循环（ReAct Loop）：**

```python
while not goal_achieved:
    observation = perceive(environment)         # 感知
    thought    = reason(observation, memory)    # 推理
    action     = decide(thought, plan)          # 决策
    result     = execute(action)                # 执行
    memory.update(observation, thought, result) # 记忆更新
    plan.adapt(result)                          # 规划调整
```

#### 2.1.1 LLM 调用编排策略

推理引擎根据任务特征自动选择最优推理策略：

```
+-----------------------------------------------------------+
|                  推理策略选择决策树                          |
|                                                             |
|  输入任务                                                    |
|      |                                                      |
|      v                                                      |
|  [是否需要外部工具/信息?]                                    |
|      |                                                      |
|      +-- 否 --> [是否需要多步推理?]                           |
|      |             |                                        |
|      |             +-- 否 --> 单步 CoT (Chain-of-Thought)    |
|      |             |           适用：简单问答、摘要、翻译     |
|      |             |                                        |
|      |             +-- 是 --> [是否存在多种可行路径?]         |
|      |                           |                          |
|      |                           +-- 否 --> 多步 CoT        |
|      |                           |       适用：数学推导、    |
|      |                           |       逻辑分析            |
|      |                           |                          |
|      |                           +-- 是 --> ToT             |
|      |                               (Tree-of-Thought)     |
|      |                               适用：创意生成、       |
|      |                               复杂决策               |
|      |                                                      |
|      +-- 是 --> ReAct (Reasoning + Acting)                  |
|                  适用：信息检索、多工具协作、                 |
|                  需要与环境交互的任务                         |
|                                                             |
+-----------------------------------------------------------+
```

| 策略 | 触发条件 | 典型场景 | Token 消耗 |
|------|---------|---------|-----------|
| 单步 CoT | 单轮推理可完成，无需工具 | 问答、摘要、翻译 | 低 |
| 多步 CoT | 多步推理，路径唯一 | 数学推导、逻辑分析 | 中 |
| ReAct | 需要工具调用或外部信息 | 搜索+整合、API 调用 | 高 |
| ToT | 多步推理，存在多种可行路径 | 创意生成、复杂决策 | 高 |

---

### 2.2 Planner - 规划模块

负责将高层目标分解为可执行的子任务序列，并在执行过程中动态调整。

```
+----------------------------------------------+
|                  Planner                      |
|                                               |
|  +--------------+  +-----------------------+ |
|  |  任务分解器   |  |     计划管理器        | |
|  | (Decomposer) |  |  (Plan Manager)       | |
|  |              |  |                       | |
|  | Goal         |  | - Plan 创建           | |
|  |   +-SubTask1 |  | - Plan 更新           | |
|  |   +-SubTask2 |  | - Plan 回滚           | |
|  |      +- ...  |  | - Plan 终止           | |
|  +--------------+  +-----------------------+ |
|                                               |
|  +--------------+  +-----------------------+ |
|  |  策略选择器   |  |     反思器            | |
|  | (Strategy)   |  |  (Reflector)          | |
|  |              |  |                       | |
|  | - 单步执行   |  | - 执行结果评估        | |
|  | - 多路径搜索 |  | - 策略有效性分析      | |
|  | - 自适应调整 |  | - 经验总结与积累      | |
|  +--------------+  +-----------------------+ |
|                                               |
+----------------------------------------------+
```

**Plan 数据结构：**

```json
{
  "plan_id": "uuid",
  "parent_plan_id": null,
  "session_id": "uuid",
  "goal": "用户原始目标",
  "priority": 5,
  "status": "running | completed | failed | paused",
  "steps": [
    {
      "step_id": 1,
      "description": "子任务描述",
      "status": "pending | running | done | failed | skipped",
      "action": "tool_call | llm_call | sub_plan",
      "dependencies": [],
      "timeout_seconds": 60,
      "result": null,
      "retry_count": 0,
      "max_retries": 3
    }
  ],
  "rollback_point": {
    "step_id": 0,
    "snapshot": {
      "completed_steps_results": {},
      "working_memory_keys": [],
      "tool_context": {}
    }
  },
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**Plan 回滚机制：**

```
Step 执行失败
   |
   v
[是否可重试?]
   |
   +-- 是 --> 重试（retry_count < max_retries）
   |              |
   |              v 重试耗尽
   +-- 否 --> [是否有回滚点?]
                  |
                  +-- 是 --> 回滚到 rollback_point 指定的 Step
                  |           - 恢复该 Step 的上下文快照
                  |           - 将后续 Step 状态重置为 pending
                  |           - 尝试替代策略重新执行
                  |
                  +-- 否 --> [是否为子计划?]
                                |
                                +-- 是 --> 标记子计划 failed，
                                |           向上传播到父计划，
                                |           父计划决定替代路径
                                |
                                +-- 否 --> 标记 Plan failed，
                                            输出已有结果 + 错误说明
```

回滚粒度说明：
- **Step 级回滚**：单个 Step 失败时，回滚到该 Step 的上一个成功检查点，尝试替代策略
- **Plan 级回滚**：多个 Step 连续失败时，回滚到 `rollback_point`，从检查点重新规划
- **子计划回滚**：子计划整体失败时，向上传播至父计划，由父计划选择替代路径

**快照 (snapshot) 内容定义：**

| 字段 | 说明 | 回滚时的恢复操作 |
|------|------|----------------|
| `completed_steps_results` | 回滚点之前已完成 Step 的执行结果 | 保留，不覆盖 |
| `working_memory_keys` | 回滚点时刻工作记忆中的关键键名列表 | 清除该时间点之后写入的工作记忆 |
| `tool_context` | 工具的上下文状态（如文件游标、API 分页偏移） | 重置为快照值 |

快照在 Plan 创建时自动生成初始版本，每完成一个 Step 后更新一次。

---

### 2.3 Memory - 记忆模块

三层记忆架构，支撑 Agent 的上下文理解和经验积累。统一使用 SQLite 作为存储引擎，降低部署复杂度。

**SQLite 并发策略：** SQLite 采用单写者模型，多任务并发场景下使用 WAL 模式 + 写队列确保安全：
- 启用 WAL 模式：`PRAGMA journal_mode=WAL`，允许读写并发
- 写操作通过异步队列串行化，避免 `SQLITE_BUSY` 错误
- MVP 单实例场景下性能足够，V1 多实例部署时切换至 PostgreSQL

```
+------------------------------------------------------+
|                      Memory                           |
|                                                       |
|  +----------------------------------------------+    |
|  |          工作记忆 (Working Memory)             |    |
|  |                                                |    |
|  |  - 当前对话上下文                               |    |
|  |  - 正在执行的 Plan 状态                         |    |
|  |  - 本轮工具调用结果                             |    |
|  |  - 生命周期：单次任务                           |    |
|  |  - 存储：进程内字典 (同步) / SQLite (持久化)    |    |
|  |  - 同步策略：每步执行后写 SQLite，任务结束时批量|    |
|  +----------------------------------------------+    |
|                                                       |
|  +----------------------------------------------+    |
|  |          短期记忆 (Short-term Memory)          |    |
|  |                                                |    |
|  |  - 近期对话历史                                 |    |
|  |  - 用户偏好与习惯                               |    |
|  |  - 最近的任务执行记录                           |    |
|  |  - 生命周期：会话级                             |    |
|  |  - 存储：SQLite                                 |    |
|  +----------------------------------------------+    |
|                                                       |
|  +----------------------------------------------+    |
|  |          长期记忆 (Long-term Memory)           |    |
|  |                                                |    |
|  |  - 领域知识库                                   |    |
|  |  - 历史任务经验与反思                           |    |
|  |  - 用户画像                                     |    |
|  |  - 生命周期：永久                               |    |
|  |  - 存储：SQLite                                 |    |
|  +----------------------------------------------+    |
|                                                       |
|  +----------------------------------------------+    |
|  |          记忆检索 (Memory Retrieval)           |    |
|  |                                                |    |
|  |  - 关键词检索：基于 SQL LIKE / FTS5 全文索引   |    |
|  |  - 时序检索：按时间倒序，近期优先               |    |
|  |  - 标签检索：按分类标签过滤                     |    |
|  |  - 综合检索：关键词 + 标签 + 时序加权排序       |    |
|  +----------------------------------------------+    |
|                                                       |
+------------------------------------------------------+
```

**SQLite 存储设计：**

```sql
-- 对话历史表
CREATE TABLE conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,          -- user / assistant / system / tool
    content TEXT NOT NULL,
    metadata TEXT,               -- JSON: 工具调用信息、Token 统计等
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 对话历史索引（高频查询字段）
CREATE INDEX idx_conversation_session ON conversation_history(session_id, created_at);

-- 记忆条目表（短期 + 长期共用，通过 type 区分）
CREATE TABLE memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,          -- short_term / long_term
    category TEXT NOT NULL,      -- preference / experience / knowledge / profile
    content TEXT NOT NULL,
    session_id TEXT,             -- 短期记忆关联会话，长期记忆为 NULL
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 记忆条目索引
CREATE INDEX idx_memory_type_category ON memory_entries(type, category);
CREATE INDEX idx_memory_session ON memory_entries(session_id);

-- 记忆标签关联表（替代 JSON 数组，支持高效标签查询）
CREATE TABLE memory_tags (
    memory_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memory_entries(id) ON DELETE CASCADE
);
CREATE INDEX idx_memory_tags_tag ON memory_tags(tag);

-- FTS5 全文索引（支持关键词检索）
CREATE VIRTUAL TABLE memory_entries_fts USING fts5(
    content,
    content=memory_entries,
    content_rowid=id
);

-- FTS5 索引同步触发器（INSERT / UPDATE / DELETE 自动维护）
-- 注意：UPDATE 触发器采用先删后插策略，MVP 单实例无并发问题；V1 多实例部署时需改用写队列串行化
CREATE TRIGGER memory_fts_insert AFTER INSERT ON memory_entries BEGIN
    INSERT INTO memory_entries_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER memory_fts_update AFTER UPDATE ON memory_entries BEGIN
    DELETE FROM memory_entries_fts WHERE rowid = old.id;
    INSERT INTO memory_entries_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER memory_fts_delete AFTER DELETE ON memory_entries BEGIN
    INSERT INTO memory_entries_fts(memory_entries_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

-- memory_tags 写入说明：
-- 标签数据由应用层在写入 memory_entries 后手动插入 memory_tags 表
-- 示例：INSERT INTO memory_tags (memory_id, tag) VALUES (1, '搜索'), (1, '失败经验');
-- 删除 memory_entries 时，ON DELETE CASCADE 自动清理关联标签

-- 记忆过期清理（短期记忆按会话生命周期管理）
-- 应用层定期执行：DELETE FROM memory_entries WHERE type='short_term' AND session_id NOT IN (活跃会话)

-- ============================================================
-- Plan 持久化表（对应 §2.2 Plan 数据结构）
-- ============================================================
CREATE TABLE plans (
    id TEXT PRIMARY KEY,            -- plan_id (UUID)
    parent_plan_id TEXT,            -- 子计划关联父计划，NULL 表示根计划
    session_id TEXT NOT NULL,       -- 关联会话，便于按会话查询历史 Plan
    goal TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'running',
    steps_json TEXT NOT NULL,       -- JSON 数组: Step 列表
    rollback_point_json TEXT,       -- JSON: snapshot 内容
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_plans_status ON plans(status);
CREATE INDEX idx_plans_parent ON plans(parent_plan_id);
CREATE INDEX idx_plans_session ON plans(session_id);

-- plans 表 updated_at 自动更新触发器
CREATE TRIGGER plans_updated AFTER UPDATE ON plans BEGIN
    UPDATE plans SET updated_at = datetime('now') WHERE id = new.id;
END;

-- memory_entries 表 updated_at 自动更新触发器
CREATE TRIGGER memory_entries_updated AFTER UPDATE ON memory_entries BEGIN
    UPDATE memory_entries SET updated_at = datetime('now'), last_accessed_at = datetime('now') WHERE id = new.id;
END;

-- ============================================================
-- 审计日志表（可观测性审计，对应 §5.2）
-- ============================================================
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT,
    step_id INTEGER,
    event_type TEXT NOT NULL,      -- thought / action / observation / result / error / plan_update
    event_category TEXT NOT NULL,   -- decision / tool_call / guardrail
    content TEXT,
    metadata TEXT,                 -- JSON: 耗时、Token 消耗等
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_plan ON audit_log(plan_id, created_at);
CREATE INDEX idx_audit_event ON audit_log(event_type, created_at);
```

**当前阶段检索策略：**

```
记忆检索请求
   |
   v
[检索类型判断]
   |
   +-- 关键词检索 --> SQLite FTS5 MATCH 查询
   |                   SELECT * FROM memory_entries_fts WHERE memory_entries_fts MATCH ?
   |                   ORDER BY rank
   |
   +-- 时序检索 ----> 按时间倒序查询
   |                   SELECT * FROM memory_entries WHERE category = ?
   |                   ORDER BY created_at DESC LIMIT ?
   |
   +-- 标签检索 ----> memory_tags 关联表查询
   |                   SELECT m.* FROM memory_entries m
   |                   JOIN memory_tags t ON m.id = t.memory_id
   |                   WHERE t.tag = ?
   |
   +-- 综合检索 ----> 关键词 + 标签 + 时序加权排序
                       得分 = 关键词匹配度 × 0.5 + 时序新鲜度 × 0.3 + 标签匹配度 × 0.2
```

**综合检索各维度得分定义：**

| 维度 | 计算方式 | 取值范围 |
|------|---------|---------|
| 关键词匹配度 | FTS5 rank 归一化：1 / (1 + rank)，rank 越小得分越高 | (0, 1] |
| 时序新鲜度 | 指数衰减：exp(-λ × Δt)，Δt 为距当前小时数，λ=0.01 | (0, 1] |
| 标签匹配度 | 命中标签数 / 查询标签数 | [0, 1] |

最终得分 = Σ(维度得分 × 权重) / Σ(权重)，归一化至 [0, 1]

---

### 2.4 Tools - 工具模块

工具是 Agent 与外部世界交互的"手和脚"。

```
+------------------------------------------------------+
|                      Tools                            |
|                                                       |
|  +--------------+  +--------------+  +------------+  |
|  | 信息获取工具  |  | 操作执行工具  |  |  代码工具   |  |
|  |              |  |              |  |            |  |
|  | - Web搜索    |  | - API调用    |  | - 代码执行  |  |
|  | - 文件读取   |  | - 数据库操作  |  | - 代码生成  |  |
|  | - 知识库查询 |  | - 消息推送    |  | - 代码审查  |  |
|  | - 数据检索   |  | - 流程触发    |  | - 沙箱运行  |  |
|  +--------------+  +--------------+  +------------+  |
|                                                       |
|  +----------------------------------------------+    |
|  |             工具注册与调度中心                  |    |
|  |            (Tool Registry & Dispatcher)        |    |
|  |                                                |    |
|  |  - 工具注册表：名称、描述、参数 Schema          |    |
|  |  - 工具发现：根据任务语义匹配候选工具           |    |
|  |  - 参数校验：基于 JSON Schema 校验输入          |    |
|  |  - 超时控制：工具执行超时自动终止               |    |
|  |  - 重试策略：指数退避重试                       |    |
|  |  - 权限管控：工具级别的访问控制                 |    |
|  +----------------------------------------------+    |
|                                                       |
+------------------------------------------------------+
```

**工具定义 Schema：**

```json
{
  "name": "web_search",
  "version": "1.0.0",
  "description": "搜索互联网获取最新信息",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "搜索关键词" },
      "max_results": { "type": "integer", "default": 5 }
    },
    "required": ["query"]
  },
  "permissions": ["network"],
  "timeout_seconds": 30,
  "retry_policy": { "max_retries": 2, "backoff": "exponential" }
}
```

**工具权限枚举：**

| 权限 | 说明 | 典型工具 |
|------|------|---------|
| `file_read` | 只读文件系统 | 文件读取、日志查看 |
| `file_write` | 写入文件系统 | 文件创建、修改、删除 |
| `network` | 网络访问 | Web 搜索、API 调用 |
| `code_exec` | 代码执行 | 代码运行、沙箱 |
| `db_access` | 数据库访问 | 数据库查询、写入 |
| `privileged` | 特权操作 | 系统配置、用户管理 |

---

## 3. 系统分层架构

```
+-------------------------------------------------------------+
|                        接入层 (Gateway)                      |
|   REST API + SSE (MVP) | WebSocket (V1) | CLI (V1) | SDK (V2)  |
|-------------------------------------------------------------|
|                      编排层 (Orchestration)                  |
|                                                               |
|   +-------------+  +--------------+  +------------------+   |
|   | Agent Core  |  |   Planner    |  |  Multi-Agent     |   |
|   |  决策中枢   |  |   规划模块   |  |  协作编排 (V2)  |   |
|   +-------------+  +--------------+  +------------------+   |
|-------------------------------------------------------------|
|                       能力层 (Capabilities)                  |
|                                                               |
|   +----------+  +----------+  +----------+  +----------+    |
|   |  Memory  |  |  Tools   |  |   LLM    |  | Guardrail|    |
|   |  记忆    |  |  工具    |  |  大模型  |  |  安全护栏|    |
|   +----------+  +----------+  +----------+  +----------+    |
|-------------------------------------------------------------|
|                       基础设施层 (Infrastructure)             |
|                                                               |
|   +-------------------------------------------------------+  |
|   |                    MVP 阶段                            |  |
|   |  +----------+  +----------+  +----------+             |  |
|   |  |  SQLite  |  | 进程内   |  | 本地日志 |             |  |
|   |  | 统一存储 |  | 缓存    |  | logging  |             |  |
|   |  +----------+  +----------+  +----------+             |  |
|   +-------------------------------------------------------+  |
|   +-------------------------------------------------------+  |
|   |                  后续演进 (V1+)                        |  |
|   |  +----------+  +----------+  +----------+             |  |
|   |  | Redis    |  |PostgreSQL|  | LangSmith|             |  |
|   |  | 缓存/锁  |  | 关系数据库|  | 可观测   |             |  |
|   |  +----------+  +----------+  +----------+             |  |
|   |  +----------+                                       |  |
|   |  |MinIO/S3 |  (文件附件，V1+)                       |  |
|   |  +----------+                                       |  |
|   +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

---

## 4. 核心流程

### 4.1 任务执行主流程

```
用户输入
   |
   v
+----------+     +--------------+     +--------------+
|  感知解析 |---->|  意图识别与  |---->|   规划生成   |
|          |     |  目标提取    |     |  Plan 生成   |
+----------+     +--------------+     +------+-------+
                                             |
                                             v
                                    +-----------------+
                                    |   Step 执行循环  |<--------+
                                    |                 |         |
                                    |  1. 选择下一步   |         |
                                    |  2. 推理决策     |         |
                                    |  3. 调用工具/LLM |         |
                                    |  4. 观察结果     |         |
                                    |  5. 更新记忆     |---------+
                                    |  6. 判断是否完成 |         |
                                    +--------+--------+         |
                                             | 完成              | 反思调整
                                             v                   |
                                    +-----------------+         |
                                    |   结果整合与    |---------+
                                    |   输出响应      |
                                    +-----------------+
```

### 4.2 流式输出机制

Agent 在执行过程中通过流式输出实时向用户反馈进展：

```
Agent Core
   |
   +-- 推理过程流式输出 (SSE / WebSocket)
   |     - thought 流：实时展示推理过程
   |     - action 流：实时展示工具调用
   |
   +-- 结果流式输出
   |     - 最终回答逐 Token 输出
   |     - 中间结果分块推送
   |
   v
接入层 (Gateway)
   |
   +-- SSE (REST API)：单向流式，适合简单场景
   +-- WebSocket：双向流式，支持用户中途干预
   +-- CLI：终端逐行输出
```

流式事件类型：

```json
{
  "event_type": "thought | action | observation | result | plan_update | error",
  "plan_id": "uuid",
  "step_id": 1,
  "content": "正在搜索相关资料...",
  "timestamp": "ISO8601"
}
```

### 4.3 异常处理流程

```
工具调用失败
   |
   +-- 可重试错误 --> 指数退避重试 --> 成功 --> 继续
   |                                    |
   |                                    v 失败
   +-- 参数错误 ----> 反思修正参数 --> 重试
   |                                    |
   |                                    v 失败
   +-- 权限不足 ----> 降级方案/通知用户
   |
   +-- 超时 --------> 缩小范围重试 / 跳过
   |
   +-- 不可恢复 ----> 终止 Plan，输出已有结果 + 错误说明
```

---

## 5. 安全与治理

### 5.1 Guardrail - 安全护栏

```
+--------------------------------------------------+
|                   Guardrail                       |
|                                                   |
|  +--------------+  +---------------------------+ |
|  |  输入护栏    |  |       输出护栏            | |
|  |  (Input)     |  |      (Output)             | |
|  |              |  |                           | |
|  | - 注入检测   |  | - 敏感信息脱敏            | |
|  | - 意图校验   |  | - 格式合规检查            | |
|  | - 频率限制   |  | - 事实性校验              | |
|  +--------------+  +---------------------------+ |
|                                                   |
|  +--------------+  +---------------------------+ |
|  |  工具护栏    |  |       行为护栏            | |
|  |  (Tool)      |  |     (Behavior)            | |
|  |              |  |                           | |
|  | - 权限校验   |  | - 预算控制 (Token/费用)   | |
|  | - 参数过滤   |  | - 循环检测 (最大步数)     | |
|  | - 沙箱隔离   |  | - 偏离度监控              | |
|  +--------------+  +---------------------------+ |
|                                                   |
+--------------------------------------------------+
```

#### 5.1.1 Prompt 注入防御方案

Prompt 注入是 Agent 系统面临的最严重安全威胁，采用三层纵深防御：

```
用户输入
   |
   v
+---------------------------------------------------------------+
|                    第一层：规则检测 (快速过滤)                   |
|                                                                 |
|  - 已知攻击模式匹配：基于正则表达式匹配常见注入模式             |
|    如："忽略以上指令"、"你现在是..."、"SYSTEM:"等               |
|  - 编码绕过检测：识别 Base64/Unicode/HTML 编码的注入尝试        |
|  - 角色扮演检测：识别试图改变 Agent 角色的指令                  |
|  - 频率异常检测：短时间内重复相似输入                           |
|                                                                 |
|  检出 --> 拒绝输入，返回安全提示                                 |
+---------------------------------------------------------------+
   | 通过
   v
+---------------------------------------------------------------+
|                    第二层：LLM 二次判断 (深度检测，可选)        |
|                                                                 |
|  - 使用独立的小模型（如 GPT-4o-mini）对输入进行安全评估         |
|  - 判断输入是否包含：                                           |
|    · 指令覆盖尝试                                               |
|    · 信息提取诱导                                               |
|    · 权限提升尝试                                               |
|  - 输出安全评分 (0-1)，阈值 < 0.7 则拦截                       |
|                                                                 |
|  注意：此层增加延迟和 Token 消耗，MVP 默认关闭，V1 启用         |
|                                                                 |
|  检出 --> 标记输入，进入隔离模式执行                             |
+---------------------------------------------------------------+
   | 通过
   v
+---------------------------------------------------------------+
|                    第三层：输入隔离 (运行时防护)                 |
|                                                                 |
|  - 系统指令与用户输入严格分离，使用不同标记包裹                 |
|    系统指令: <system-instruction>...</system-instruction>       |
|    用户输入:   <user-input>...</user-input>                     |
|  - 在 Prompt 中明确告知 LLM：用户输入不可信，不可覆盖系统指令  |
|  - 工具调用参数额外校验，防止通过工具参数注入                   |
|                                                                 |
+---------------------------------------------------------------+
```

#### 5.1.2 偏离度监控定义

偏离度用于衡量 Agent 当前行为与原始目标的偏移程度：

**MVP 阶段：关键词重叠度（Jaccard 相似度）**

```
偏离度 = 1 - JaccardSimilarity(当前 Step 关键词集, 目标关键词集)

计算方式：
  1. 对用户原始目标提取关键词集合 K_goal（分词 + 去停用词）
  2. 对当前 Step 描述提取关键词集合 K_step
  3. Jaccard 相似度 = |K_goal ∩ K_step| / |K_goal ∪ K_step|
  4. 偏离度 = 1 - Jaccard 相似度
```

**V1 阶段：语义相似度（Embedding 余弦相似度）**

```
偏离度 = 1 - CosineSimilarity(当前行为向量, 目标向量)

计算方式：
  1. 将用户原始目标编码为向量 E_goal（使用 LLM embedding）
  2. 将当前 Step 的描述编码为向量 E_step
  3. 偏离度 = 1 - cos(E_goal, E_step)
```

**阈值定义（两个阶段共用）：**

```
  - 偏离度 < 0.3：正常，目标一致
  - 0.3 ≤ 偏离度 < 0.6：警告，可能偏离，记录日志
  - 偏离度 ≥ 0.6：严重偏离，暂停执行，请求用户确认

衰减机制：
  - 允许中间步骤存在合理偏离（如搜索步骤与目标间接相关）
  - 对连续 N 步偏离度 > 0.3 的情况升级为严重偏离
```

### 5.2 可观测性

| 维度 | MVP 实现 | V1+ 实现 |
|------|---------|---------|
| 决策追踪 | SQLite 审计表记录每步 thought / action / observation | LangSmith 集成，可视化链路 |
| 工具审计 | SQLite 审计表记录输入、输出、耗时、状态 | LangSmith 集成 |
| Token 统计 | 进程内计数器，按 session / task 维度统计 | LangSmith Token 统计面板 |
| 链路追踪 | 本地日志 + SQLite 审计表 | OpenTelemetry / LangSmith 集成 |
| 日志分级 | Python logging，DEBUG / INFO / WARN / ERROR 分级输出 | 同左 + 结构化日志输出 |

---

## 6. 项目目录结构

```
cfa-agent/
|-- src/
|   |-- api/                    # 接入层
|   |   |-- server.py           # HTTP/WebSocket 服务启动
|   |   |-- routes/             # 路由定义
|   |   |   |-- chat.py         # 对话接口 (REST + SSE)
|   |   |   +-- ws.py           # WebSocket 接口
|   |   +-- middleware/          # 中间件
|   |       +-- rate_limit.py   # 限流中间件
|   |
|   |-- core/                   # Agent 核心模块
|   |   |-- agent.py            # Agent 主类，决策循环
|   |   |-- perception.py       # 感知引擎
|   |   |-- reasoning.py        # 推理引擎
|   |   +-- decision_dispatcher.py  # 决策调度器
|   |
|   |-- planner/                # 规划模块
|   |   |-- planner.py          # 规划器主类
|   |   |-- decomposer.py       # 任务分解
|   |   |-- strategy.py         # 策略选择
|   |   +-- reflector.py        # 反思器
|   |
|   |-- memory/                 # 记忆模块
|   |   |-- base.py             # 记忆抽象基类
|   |   |-- working_memory.py   # 工作记忆
|   |   |-- short_term.py       # 短期记忆
|   |   |-- long_term.py        # 长期记忆
|   |   |-- retrieval.py        # 记忆检索
|   |   +-- sqlite_store.py     # SQLite 存储引擎（建表、CRUD、FTS5）
|   |
|   |-- tools/                  # 工具模块
|   |   |-- registry.py         # 工具注册中心
|   |   |-- tool_dispatcher.py  # 工具调度
|   |   |-- base.py             # 工具基类
|   |   |-- web_search.py       # Web 搜索工具
|   |   |-- code_runner.py      # 代码执行工具
|   |   +-- file_ops.py         # 文件操作工具
|   |
|   |-- guardrail/              # 安全护栏
|   |   |-- input_guard.py      # 输入护栏
|   |   |-- output_guard.py     # 输出护栏
|   |   |-- tool_guard.py       # 工具护栏
|   |   +-- behavior_guard.py   # 行为护栏
|   |
|   |-- llm/                    # 大模型适配层
|   |   |-- base.py             # LLM 抽象基类
|   |   |-- openai_adapter.py   # OpenAI 适配
|   |   |-- prompt_manager.py   # Prompt 模板管理
|   |   +-- token_counter.py    # Token 计数与截断
|   |
|   |-- prompts/                # Prompt 模板资产
|   |   |-- system/             # 系统级 Prompt
|   |   |   |-- agent_role.yaml     # Agent 角色定义
|   |   |   +-- safety_rules.yaml   # 安全规则
|   |   |-- reasoning/           # 推理策略 Prompt
|   |   |   |-- cot.yaml            # Chain-of-Thought
|   |   |   |-- react.yaml          # ReAct
|   |   |   +-- reflect.yaml        # 反思
|   |   +-- tools/               # 工具调用 Prompt
|   |       +-- tool_call.yaml      # 工具调用模板
|   |
|   |-- models/                 # 数据模型定义
|   |   |-- plan.py             # Plan / Step 模型
|   |   |-- tool.py             # Tool 定义模型
|   |   |-- memory.py           # Memory 数据模型
|   |   +-- message.py          # 消息与事件模型
|   |
|   +-- common/                 # 公共模块
|       |-- config.py           # 配置管理
|       |-- logger.py           # 日志
|       +-- exceptions.py       # 异常定义
|
|-- tests/                      # 测试
|   |-- test_api/
|   |-- test_core/
|   |-- test_planner/
|   |-- test_memory/
|   |-- test_tools/
|   +-- test_guardrail/
|
|-- config/                     # 配置文件
|   |-- default.yaml            # 默认配置
|   |-- tools.yaml              # 工具配置
|   +-- guardrail.yaml          # 安全护栏配置
|
|-- pyproject.toml              # 项目元数据与依赖
+-- doc/                        # 文档
    +-- architecture.md         # 本架构文档
```

---

## 7. 关键技术选型

### MVP 阶段（零外部服务依赖）

| 领域 | 选型 | 理由 |
|------|------|------|
| 编程语言 | Python 3.11+ | AI 生态最成熟，异步支持完善 |
| LLM 框架 | OpenAI API / 兼容接口 + LiteLLM | 主流且可替换，LiteLLM 提供多模型统一适配与 Token 计数 |
| 统一存储 | SQLite | 零外部服务：对话历史、记忆条目、Plan 历史、审计日志全部使用 SQLite，FTS5 支持全文检索 |
| 缓存 | Python 标准库 `functools.lru_cache` / 进程内字典 | MVP 单实例无需外部缓存 |
| 异步框架 | asyncio (Windows 开发) / asyncio + uvloop (Linux 生产) | uvloop 仅支持 Linux/macOS，Windows 使用默认事件循环 |
| 可观测 | Python logging + SQLite 审计表 | 零依赖，本地日志 + 结构化审计 |
| 配置管理 | Pydantic Settings | 类型安全、环境变量支持 |
| 测试 | pytest + pytest-asyncio | 异步测试支持完善 |
| Web 框架 | FastAPI | 原生异步、SSE/WebSocket 支持、自动 OpenAPI 文档 |

### 后续演进（V1+）

| 领域 | 选型 | 理由 | 引入版本 |
|------|------|------|---------|
| 关系数据库 | PostgreSQL | 生产环境高并发场景替换 SQLite | V1 |
| 缓存 | Redis | 会话管理、分布式锁、短期记忆 | V1 |
| 可观测 | LangSmith + OpenTelemetry | Agent 链路追踪最佳实践 | V1 |
| 对象存储 | MinIO (开发) / S3 兼容 (生产) | 文件类工具的附件存储 | V1+ |

---

## 8. 扩展性设计

### 8.1 Multi-Agent 协作（V2 演进设计）

> 以下为 V2 阶段设计，MVP 和 V1 均为单 Agent 架构。此处提前设计以确保架构可扩展性。

```
+-----------------------------------------------------------+
|              Multi-Agent Orchestrator                       |
|                                                             |
|  +----------+  +----------+  +--------------+             |
|  | Planner  |  | Coder    |  | Reviewer     |             |
|  | Agent    |  | Agent    |  | Agent        |             |
|  +----+-----+  +----+-----+  +------+-------+             |
|       |              |               |                      |
|       +--------------+---------------+                      |
|                      |                                      |
|              +-------v--------+                             |
|              |  共享记忆空间   |                             |
|              | (Shared Memory)|                             |
|              +----------------+                             |
+-----------------------------------------------------------+
```

#### 8.1.1 Agent 间通信协议

```
+-----------------------------------------------------------+
|                  Agent 通信消息格式                          |
|                                                             |
|  {                                                          |
|    "msg_id": "uuid",                                        |
|    "from_agent": "planner_agent",                           |
|    "to_agent": "coder_agent",                               |
|    "msg_type": "task_assign | result_report |               |
|                 clarification | handoff",                   |
|    "payload": {                                             |
|      "task": "实现用户认证模块",                             |
|      "context": { ... },                                    |
|      "constraints": [ ... ]                                 |
|    },                                                       |
|    "priority": 5,                                           |
|    "timestamp": "ISO8601"                                   |
|  }                                                          |
+-----------------------------------------------------------+
```

| 消息类型 | 说明 | 典型场景 |
|---------|------|---------|
| task_assign | 分配子任务 | Planner 向 Coder 分配编码任务 |
| result_report | 汇报执行结果 | Coder 向 Reviewer 提交代码审查 |
| clarification | 请求澄清 | 执行者向分配者询问不明确的需求 |
| handoff | 任务移交 | 当前 Agent 无法完成，移交给更合适的 Agent |

#### 8.1.2 任务分配策略

```
新任务到达
   |
   v
[任务类型匹配]
   |
   +-- 编码类 --> Coder Agent
   +-- 分析类 --> Analyst Agent
   +-- 审查类 --> Reviewer Agent
   +-- 规划类 --> Planner Agent
   |
   v
[负载均衡]
   |
   +-- 同类型多实例时，选择当前负载最低的 Agent
   |
   v
[能力检查]
   |
   +-- 检查目标 Agent 是否具备所需工具权限
   +-- 检查是否超出并发任务上限
   +-- 不满足时回退到通用 Agent 或等待
```

#### 8.1.3 冲突解决机制

| 冲突类型 | 解决策略 |
|---------|---------|
| 资源竞争（同一工具） | 基于任务优先级排队，高优先级先执行 |
| 结果冲突（不同 Agent 结论矛盾） | Reviewer Agent 仲裁，或提交用户裁决 |
| 死锁（循环等待） | 超时自动释放 + 全局死锁检测 |
| 权限冲突 | 最小权限原则，拒绝越权操作 |

#### 8.1.4 共享记忆并发控制

- **读写锁**：读操作共享锁，写操作排他锁
- **乐观并发**：基于版本号的 CAS 机制，适用于低冲突场景
- **事件通知**：记忆更新时发布事件，相关 Agent 订阅并刷新本地缓存

### 8.2 插件化工具扩展

- 工具通过装饰器注册，自动生成 Schema
- 支持运行时动态加载/卸载工具
- 工具权限分级：只读 / 读写 / 特权
- 工具版本管理：Schema 中包含 `version` 字段，注册中心维护版本兼容性映射

### 8.3 模型热切换

- LLM 适配层抽象，支持运行时切换模型
- 不同任务可路由到不同模型（如简单任务用小模型，复杂推理用大模型）
- 支持本地模型 / 云端模型混合部署
- 通过 LiteLLM 统一适配，屏蔽不同模型 API 差异

---

## 9. 性能指标与 SLA

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 单步推理延迟 | < 5s (P95) | 不含工具调用，仅 LLM 推理时间 |
| 端到端任务延迟 | < 60s (P95) | 简单任务（3 步以内） |
| 最大并发任务数 | 100 | 单实例并发执行的任务数 |
| 流式首 Token 延迟 | < 2s | 从用户输入到首个 Token 输出 |
| Token 消耗预算 | 可配置 | 按会话设置上限，超出暂停并通知 |
| 工具调用超时 | 30s (默认) | 可按工具自定义 |
| 系统可用性 | 99.9% | 生产环境目标 |

---

## 10. 部署架构

### 10.1 开发环境（单机，MVP）

```
+-------------------------------------------+
|            开发者本地机器                   |
|                                             |
|  +--------+  +--------------+             |
|  | FastAPI |  | SQLite       |             |
|  | :8000   |  | (文件)       |             |
|  +--------+  +--------------+             |
|                                             |
|  +----------------------------+            |
|  | OpenAI API (云端)          |            |
|  +----------------------------+            |
+-------------------------------------------+

零外部服务依赖：无需安装 Redis / PostgreSQL / MinIO 等外部服务，pip install 即可运行。
```

### 10.2 生产环境（分布式）

```
+-----------------------------------------------------------+
|                       负载均衡 (Nginx)                      |
|                                                             |
|  +------------+  +------------+  +------------+            |
|  | API 实例 1 |  | API 实例 2 |  | API 实例 N |            |
|  +-----+------+  +-----+------+  +-----+------+            |
|        |               |               |                    |
|        +---------------+---------------+                    |
|                        |                                    |
|  +---------------------v--------------------------------+  |
|  |                    共享存储层                          |  |
|  |                                                        |  |
|  |  +----------+  +----------+  +----------+             |  |
|  |  | Redis    |  |PostgreSQL|  | MinIO/S3 |             |  |
|  |  | Cluster  |  | Cluster  |  |          |             |  |
|  |  +----------+  +----------+  +----------+             |  |
|  +-------------------------------------------------------+  |
|                                                             |
|  +-------------------------------------------------------+  |
|  |                   外部服务                              |  |
|  |  OpenAI API / 自部署模型 / LangSmith                   |  |
|  +-------------------------------------------------------+  |
+-----------------------------------------------------------+
```

---

## 11. 版本演进路线图

### MVP (v0.1)

- Agent Core：ReAct 循环 + 单步 CoT
- Planner：基础任务分解 + 单路径执行
- Memory：工作记忆 + 短期记忆 + 长期记忆，全部基于 SQLite 存储，FTS5 全文检索
- Tools：3-5 个核心工具（Web 搜索、文件操作、代码执行）
- Guardrail：输入注入检测（规则检测 + 输入隔离）+ 输出脱敏
- 接入层：REST API + SSE 流式输出
- 可观测性：Python logging + SQLite 审计表
- 缓存：进程内字典 / lru_cache
- 存储：SQLite 统一存储（零外部服务依赖，pip install 即可运行）

### V1 (v1.0)

- 推理策略：ReAct + 多步 CoT + 反思
- Planner：Plan 回滚 + 策略选择
- Memory：长期记忆增强，偏离度监控升级为 Embedding 余弦相似度
- Tools：插件化工具注册 + 动态加载
- Guardrail：完整四维护栏 + Prompt 注入三层防御（含 LLM 二次判断）
- 接入层：WebSocket + CLI
- 可观测性：LangSmith 集成 + Token 统计
- 缓存：Redis（会话管理、分布式锁）
- 存储：SQLite → PostgreSQL（生产环境）
- 对象存储：MinIO / S3（文件附件）

### V2 (v2.0)

- Multi-Agent 协作：多 Agent 编排 + 共享记忆
- 推理策略：Tree-of-Thought
- 模型热切换：多模型路由 + 本地/云端混合
- 生产部署：分布式架构 + 高可用
- SDK：Python SDK 供第三方集成