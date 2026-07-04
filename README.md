# CFA-Agent 自主决策智能体

基于大语言模型的自主决策智能体系统，具备意图识别、多步规划、工具调用、行为护栏和记忆管理等核心能力。

## 系统架构

```
用户输入 → 感知引擎(意图识别) → Agent Core → 推理引擎(CoT/ReAct)
                                    ↓                    ↓
                               规划器(Planner)      工具调度(Tools)
                                    ↓                    ↓
                               护栏系统(Guardrails)  记忆系统(Memory)
                                    ↓
                               执行输出 → 用户
```

**核心模块：**

| 模块 | 路径 | 职责 |
|------|------|------|
| Agent Core | `src/core/` | 决策中枢，协调感知、推理、规划、执行 |
| 感知引擎 | `src/core/perception.py` | LLM 驱动的意图识别 |
| 推理引擎 | `src/core/reasoning.py` | CoT / ReAct / Simple Chat 推理策略 |
| 规划器 | `src/planner/` | 任务分解、计划管理、执行反思 |
| 护栏系统 | `src/guardrails/` | 输入/输出/行为/工具四重安全护栏 |
| 工具模块 | `src/tools/` | 网络搜索、代码执行、文件操作 |
| 记忆系统 | `src/memory/` | 短期/长期/工作记忆 + FTS5 检索 |
| LLM 适配 | `src/llm/` | OpenAI 兼容接口、提示模板管理、Token 计数 |
| API 服务 | `src/api/` | FastAPI 路由，支持普通和 SSE 流式响应 |
| 前端界面 | `ui/` | React 19 + Tailwind CSS 聊天界面 |

## 环境要求

- **Python** 3.11+
- **Node.js** 18+（前端开发）
- **操作系统**：Windows / macOS / Linux

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd cfa-agent
```

### 2. 配置环境变量

复制示例文件并填写配置：

```bash
cp .env.example .env
```

编辑 `.env`，必须配置以下项：

```env
# LLM 配置（必填）
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_REASONING=gpt-4o

# 应用配置
APP_HOST=127.0.0.1
APP_PORT=8000
APP_DEBUG=true
```

> 支持任何 OpenAI 兼容 API（如 Azure OpenAI、DeepSeek、商汤日日新等），只需修改 `OPENAI_BASE_URL` 和对应的模型名称。

### 3. 启动后端

```bash
# 安装依赖（推荐使用虚拟环境）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"

# 启动服务
python -m src.main
```

后端默认运行在 `http://127.0.0.1:8000`。

验证服务是否启动成功：

```bash
curl http://127.0.0.1:8000/docs
```

### 4. 启动前端

```bash
cd ui

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端默认运行在 `http://localhost:3000`，自动代理 API 请求到后端 `8000` 端口。

浏览器打开 `http://localhost:3000` 即可使用。

## API 接口

### 普通聊天

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": "test-1"}'
```

### 流式聊天（SSE）

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我搜索Python最新版本", "session_id": "test-2", "stream": true}'
```

### 接口文档

启动后端后访问 `http://127.0.0.1:8000/docs` 查看 Swagger UI。

## 项目结构

```
cfa-agent/
├── .env                    # 环境变量配置
├── .env.example            # 环境变量示例
├── pyproject.toml          # Python 项目配置
├── config/
│   ├── default.yaml        # 默认应用配置
│   ├── guardrail.yaml      # 护栏配置
│   └── tools.yaml          # 工具配置
├── src/
│   ├── main.py             # 入口文件
│   ├── api/                # FastAPI 路由与依赖
│   ├── core/               # Agent 核心（感知、推理、决策）
│   ├── agent/              # 计划执行器、步骤执行器
│   ├── planner/            # 规划器、反思器
│   ├── guardrails/         # 安全护栏系统
│   ├── llm/                # LLM 适配器、提示管理、Token 计数
│   ├── memory/             # 记忆存储与检索
│   ├── models/             # 数据模型定义
│   ├── tools/              # 工具实现
│   └── prompts/            # 提示模板（YAML）
│       ├── intent/         # 意图识别模板
│       ├── reasoning/      # 推理策略模板
│       ├── system/         # 系统角色模板
│       └── tools/          # 工具调用模板
├── ui/                     # React 前端
│   ├── src/
│   │   ├── api.ts          # API 通信层
│   │   ├── hooks/          # 自定义 Hooks
│   │   └── components/     # UI 组件
│   ├── package.json
│   └── vite.config.ts
├── tests/                  # 测试用例
├── data/                   # SQLite 数据库文件
├── logs/                   # 运行日志
└── doc/                    # 架构设计文档
```

## 开发命令

### 后端

```bash
# 运行测试
pytest

# 代码检查
ruff check src/

# 启动服务（开发模式，自动重载）
python -m src.main
```

### 前端

```bash
cd ui

# 开发服务器
npm run dev

# 类型检查
npx tsc --noEmit

# 代码检查
npm run lint

# 生产构建
npm run build
```

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `OPENAI_API_KEY` | ✅ | - | LLM API 密钥 |
| `OPENAI_BASE_URL` | ✅ | - | LLM API 地址 |
| `OPENAI_MODEL` | ✅ | - | 对话模型名称 |
| `OPENAI_MODEL_REASONING` | ✅ | - | 推理模型名称 |
| `OPENAI_MAX_TOKENS_PER_REQUEST` | ❌ | `4096` | 单次请求最大 Token 数 |
| `OPENAI_TEMPERATURE` | ❌ | `0.7` | 生成温度 |
| `APP_HOST` | ❌ | `127.0.0.1` | 服务监听地址 |
| `APP_PORT` | ❌ | `8000` | 服务监听端口 |
| `APP_DEBUG` | ❌ | `true` | 调试模式（自动重载） |
| `SQLITE_DB_PATH` | ❌ | `./data/cfa_agent.db` | 数据库文件路径 |
| `LOG_LEVEL` | ❌ | `DEBUG` | 日志级别 |
| `LOG_FILE` | ❌ | `./logs/cfa_agent.log` | 日志文件路径 |
| `BEHAVIOR_MAX_STEPS` | ❌ | `20` | 单次计划最大执行步骤数 |
| `BEHAVIOR_TOKEN_BUDGET` | ❌ | `256000` | 单次计划 Token 预算 |
| `BEHAVIOR_CONSECUTIVE_DEVIATION_LIMIT` | ❌ | `5` | 连续偏离次数上限 |