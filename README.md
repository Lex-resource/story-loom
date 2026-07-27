# Novel Assistant

AI 驱动的小说创作助手：通过多智能体流水线自动生成、审阅、校验小说章节，并维护贯穿全文的世界观、人物、伏笔等知识图谱。

## 功能特性

- **多智能体流水线**：策划 → 写作 → 编辑 → 校验 → 提取，五步串联自动生成章节
- **双创作模式**：长篇网文（默认 100 章/连载）与知乎短篇（默认 3 节/完结）
- **知识图谱**：世界观、人物状态、伏笔账本、主线进度四类活文档，随章节演进自动更新
- **向量检索**：基于 ChromaDB 的 RAG 上下文召回，保证长篇连贯性
- **实时流式输出**：WebSocket 推送生成日志与流式文本块
- **多 LLM 支持**：DeepSeek / OpenAI / Moonshot / 智谱 / 通义，支持主备故障转移
- **章节版本控制**：发布快照、回滚、Commit 历史
- **本地访问控制**：默认仅 localhost 访问，可配置远程开关

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI 0.115 + Uvicorn + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL（asyncpg 驱动，**唯一支持**） |
| 数据库迁移 | Alembic |
| 向量数据库 | ChromaDB 0.5 |
| 前端 | React 19 + Vite 8 + Zustand + vis-network |
| Python | >= 3.11 |

## 环境要求

- Python 3.11+
- Node.js 18+（前端构建）
- PostgreSQL 14+

## 快速开始

### 1. 克隆并安装依赖

```bash
# 后端
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

# 前端
cd frontend
npm install
cd ..
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的配置：

```bash
cp .env.example .env
```

关键字段：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | PostgreSQL 连接串，格式 `postgresql+asyncpg://user:pass@host:5432/novel_assistant` |
| `LLM_BASE_URL` | LLM API 地址（如 `https://api.deepseek.com`） |
| `LLM_API_KEY` | LLM API Key |
| `LLM_MODEL` | 模型名（如 `deepseek-chat`） |
| `EMBEDDING_MODEL` | 向量嵌入模型（留空则回退到 LLM_* 配置） |
| `DISABLE_IN_PROCESS_WORKER` | `true` 时使用独立 worker 进程，`false` 时由后端内嵌 |

### 3. 初始化数据库

确保 PostgreSQL 已运行并创建了数据库，然后执行迁移：

```bash
python scripts/migrate_db.py
```

### 4. 启动服务

**方式一：独立 worker（推荐生产环境）**

在 `.env` 中设置 `DISABLE_IN_PROCESS_WORKER=true`，然后分别启动：

```bash
# 终端 1：后端 API
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端 2：后台 worker
python worker.py

# 终端 3：前端开发服务器
cd frontend && npm run dev
```

**方式二：内嵌 worker（开发环境）**

在 `.env` 中设置 `DISABLE_IN_PROCESS_WORKER=false`，后端会自动启动 worker 循环，只需启动后端和前端。

**Windows 一键启动**

```bash
start_all.bat
```

> 注意：使用前请确保 `python` 和 `npm` 已加入系统 PATH。

### 5. 访问应用

- 前端开发服务器：http://localhost:5173
- 后端 API：http://localhost:8000
- 健康检查：http://localhost:8000/health

## 项目结构

```
novel-assistant/
├── main.py                 # FastAPI 入口
├── worker.py               # 后台 worker 入口
├── config.py               # 配置（从 .env 加载）
├── database.py             # 数据库引擎
├── routers/                # API 路由
│   ├── projects.py         # 项目 CRUD、大纲
│   ├── pipeline.py         # 生成、暂停、恢复
│   ├── chapters.py         # 章节管理
│   ├── issues.py           # 问题与 Token 统计
│   ├── knowledge.py        # 向量检索
│   ├── knowledge_views.py  # 知识图谱视图
│   ├── living_docs.py      # 活文档
│   ├── settings.py         # LLM 配置
│   ├── stream.py           # WebSocket 实时流
│   └── system_configs.py   # 流水线配置
├── agents/                 # AI 智能体
│   ├── writing/            # 策划/写作/编辑/校验/提取
│   └── pipeline.py         # 流水线节点注册
├── services/               # 业务逻辑层
├── worker_support/         # 后台任务编排
├── models/                 # SQLAlchemy ORM 模型
├── alembic/                # 数据库迁移
├── prompts/                # 提示词模板（JSON）
├── frontend/               # React 前端
├── scripts/                # 运维脚本
├── tests/                  # 测试
└── docs/                   # 文档
```

## 提示词模板

`prompts/` 下按 `{extraction,planning,validation,writing}/{long_webnovel,zhihu_short}.json` 组织。应用启动时会自动将模板种子到数据库 `prompt_templates` 表，数据库为运行时权威来源。可在「系统配置」页面在线编辑。

## 许可证

[MIT License](LICENSE)
