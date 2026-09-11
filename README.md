# Novel Assistant

AI 驱动的小说创作助手：通过多智能体流水线自动生成、审阅、校验小说章节，并维护贯穿全文的世界观、人物、伏笔等知识图谱。

## 功能特性

- **多智能体流水线**：策划 → 写作 → 编辑 → 校验 → 提取，五步串联自动生成章节
- **双创作模式**：长篇网文（默认 100 章/连载）与知乎短篇（默认 3 节/完结）
- **知识图谱**：世界观、人物状态、伏笔账本、主线进度四类活文档，随章节演进自动更新
- **角色卡 authority**：AI 生成完整角色卡，用户可覆盖编辑；修改前快照与修改记录独立保存，角色卡是人物写作事实源
- **稀疏章节状态**：角色只有在本章状态真正变化时才写入章节状态，支持按章节恢复角色当时的状态
- **只读人物志**：人物志由角色卡、状态和结构化关系确定性生成并持久化，用于 Planner 摘要和关系图，不允许直接编辑
- **向量检索**：基于 ChromaDB 的 RAG 上下文召回，保证长篇连贯性
- **分层小说记忆**：Evidence、Memory Atom、Scene Block 和 Project Doctrine 按项目/支线/故事线隔离，支持可追溯候选、版本演进和渐进召回（详见 `docs/novel-memory.md`）
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
| `DISABLE_IN_PROCESS_WORKER` | `false`（默认）由后端内嵌 worker 单进程运行；`true` 时使用独立 worker.py 进程 |

### 3. 初始化数据库

确保 PostgreSQL 已运行并创建了数据库，然后执行迁移：

```bash
python scripts/migrate_db.py
```

### 4. 启动服务

**方式一：单进程（默认，推荐）**

`.env` 保持 `DISABLE_IN_PROCESS_WORKER=false`（默认值），后端会自动内嵌 worker 循环，只需启动后端和前端。

> ⚠️ 单进程模式下**不要**用 `uvicorn --reload` 启动后端：每次热重载都会重启内嵌 worker，丢掉内存中的在跑任务并留下孤儿 RUNNING 行（`--reload` 只适合纯 API 开发）。

```bash
# 终端 1：后端 API（内嵌 worker）
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端 2：前端开发服务器
cd frontend && npm run dev
```

**方式二：独立 worker（外部模式，可选）**

在 `.env` 中设置 `DISABLE_IN_PROCESS_WORKER=true`，然后分别启动：

```bash
# 终端 1：后端 API
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端 2：后台 worker
python worker.py

# 终端 3：前端开发服务器
cd frontend && npm run dev
```

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
│   ├── characters.py       # 角色卡、人物志投影、状态和修改记录
│   ├── issues.py           # 问题与 Token 统计
│   ├── knowledge.py        # 向量检索
│   ├── knowledge_views.py  # 知识图谱视图
│   ├── novel_memory.py     # 分层记忆
│   ├── character_branches.py # 角色分支
│   ├── settings.py         # LLM 配置
│   ├── stream.py           # WebSocket 实时流
│   ├── system_configs.py   # 工作流/运行参数配置
│   └── worker_admin.py     # worker 控制面(队列/暂停/取消/重试)
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

## 角色卡数据流

`CharacterCard` 是角色的唯一可编辑事实源。AI 初次生成和用户编辑都走同一套事务：覆盖当前卡、保存一份修改前快照、写入一条修改记录、同步结构化关系并刷新只读 `CharacterManifest`。

Planner 只读取人物志摘要来选择本章角色并生成 `character_goals`；Writer、Editor、Validator 和 Extractor 只对本章涉及角色读取完整角色卡及上一章状态。`CharacterChapterState` 是稀疏历史，某章没有状态变化就不会新增记录。

角色卡表结构由标准 Alembic 迁移建表（`python scripts/migrate_db.py`），**没有**额外的数据迁移脚本。角色卡内容由角色卡页编辑或 AI 建卡生成；旧 `settings_docs` 人物志保留原样不自动转换，旧 `character_state` 接口保留为只读兼容投影，角色卡页是唯一编辑入口。

## 角色支线

角色支线使用独立的 `character_branches` 与 `character_branch_chapters` 表，不复用主线 `chapters`。支线创建时冻结主线锚点上下文，Planner、Writer、Editor、Validator 只在支线域内工作；支线正文可以编辑，但不会修改主线章节、角色卡、人物志或主线关系。支线章节的向量投影使用独立命名空间，归档时清理该命名空间，不会进入主线项目集合。角色页的“自动发现候选”开关默认关闭，开启后也只生成候选，不会自动调用模型生成正文。

## 提示词模板

`prompts/` 下按 `{extraction,planning,validation,writing}/{long_webnovel,zhihu_short}.json` 组织。应用启动时会自动将模板种子到数据库 `prompt_templates` 表，数据库为运行时权威来源。可在「系统配置」页面在线编辑。

## 许可证

[MIT License](LICENSE)
