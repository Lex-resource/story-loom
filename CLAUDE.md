# CLAUDE.md

AI 小说创作助手。FastAPI + React,五智能体流水线自动生成、审阅、校验章节,并维护贯穿全文的分层记忆。

## 这个仓库有两重身份

**生产应用**冻结在提示词版本 **A28/V43**,决策依据见 `docs/research/novel-memory-continuity/PRODUCTION.md`(十章实验:七维平均 8.601、9/9 章零内容重试、连续性 9.000、平均记忆上下文 ~6036 字符)。

**研究平台**保存 V0–V66 与 Ariadne A0–A52 共 78 个实验版本,位于 `research/`。生产代码**不含任何版本分支**;研究变体通过唯一接缝 `services/version_surface.py` 接入。

这个分离由架构测试强制(见下)。改动前先读 `tests/architecture/test_service_boundaries.py`。

## 常用命令

```bash
# 测试(全量约 10-15s,具体数量以 pytest -q 为准)
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest tests/architecture/ -q      # 边界约束
.venv/Scripts/python.exe -m pytest tests/research/ -q          # 研究版本
.venv/Scripts/python.exe -m pytest tests/worker_support/test_generation_trace.py -q   # 生成流程 golden trace

# 后端 / worker / 前端
python -m uvicorn main:app --host 127.0.0.1 --port 8000
python worker.py
cd frontend && npm run dev          # 或 npm run check(门禁:format:check + lint + build)

# 数据库迁移(只走 Alembic)
python scripts/migrate_db.py

# 存储一致性
python scripts/reconcile_storage.py [--repair]
```

环境:Windows + PowerShell,虚拟环境在 `.venv/`。`data/` 有 1.4 GB 研究产物,已被 gitignore。

## 硬约束

违反下列任一条会被测试或运行时拒绝:

1. **`services/` 不得导入 `worker_support/`** —— AST 测试强制。这也决定了工作流图的分层:
   模型与校验器在 `services/chapter_graph.py`（router 写入时要校验),解释器在
   `worker_support/chapter_graph_runner.py`。
2. **生产代码不得出现提示词版本门** —— 不得调用 `prompt_version_at_least`/`prompt_version`。唯一例外是接缝 `services/version_surface.py`。需要版本相关行为时,在 `research/prompt_versions/` 注册一个表面。
3. **生产代码不得依据 `ExperimentContext.variant` 分支** —— 把 variant 写进事件记录是允许的(`experiment_recorder` 的本职),用它做判断不行。
4. **`research/` 只能在接缝函数内部被导入** —— 部署时可以完全不包含该目录;`research_override` 用 `ImportError` 兜住缺失。
5. **`DATABASE_URL` 必须是 `postgresql+asyncpg://`** —— `config.py:16` 强校验,SQLite 不受支持。
6. **不使用 `Base.metadata.create_all()`** —— 只走 Alembic 迁移。
7. **修改提示词表面等于修改生产行为** —— 先更新黄金快照(见下)并在说明里给出理由。
8. **不得按 `novel_format == NOVEL_FORMAT_ZHIHU_SHORT` 判断短篇** —— 用
   `services/workflow_surface.is_short_form_workflow()`。工作流可自定义之后,克隆自短篇的
   工作流会拿到短篇提示词却走长篇 schema/记忆合并 —— 提示词对了结构错了,最难查的一类。
9. **resume 锚点只能是 5 个 agent 名** —— `job.current_step` / `chapter.pipeline_step` 的
   取值域。细粒度阶段(11 个角色)怎么编排都不影响恢复,全靠这一条。
   `tests/worker_support/test_chapter_steps_anchors.py` 对源码做 AST 检查。
10. **改动单章生成流程前先跑 golden trace** —— 见下。

## 提示词表面与黄金快照

`tests/fixtures/v43_production_surface.json` 逐字节锁定 A28/V43 的生产表面:5 个 agent 的完整 system/user prompt、交接包在多个预算下的渲染、契约规范化结果、Validator 的重试分类判定、上下文预算数值。

有意修改提示词时:

```bash
V43_SNAPSHOT_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/test_v43_production_surface_snapshot.py
```

三条不变量由该文件的测试保证:

- 无 `ExperimentContext` 的生产表面 **等于** pin `V43 + ariadne-a28` 的表面
- 在生产冻结点上,研究覆盖层对每个已注册表面**让路**(返回 `NO_OVERRIDE`),使 pin A28/V43 的复现走生产同一条代码路径
- 偏离冻结点的版本(如 V50/V66)确实拿到覆盖 —— 证明这是"分离"而非"删除"

`NOVEL_CONTINUITY_PROMPT_VERSION` 现在是**研究专用**。在 `.env` 里把它改成 V50 之类不会改变生产行为;`main.py`/`worker.py` 启动时会对偏离 V43 的取值发 warning。

## 单章生成的 golden trace

`tests/worker_support/test_generation_trace.py` 的 **20 条序列**是「改了编排但没改行为」的
唯一硬证据:它把所有 LLM/DB 侧的 flow 函数 stub 掉,只记录阶段调用顺序与关键决策点
(含 `set_job_step`,因为 resume 依赖 `job.current_step` 的取值)。

动 `worker_support/chapter_steps.py`、`chapter_graph_runner.py`、`generate_job_runner.py`
或 `services/chapter_graph.py` 之前先跑它。**序列对不上就回退,不要改序列** —— 改 trace
等于承认行为变了。

它刻意**不** stub `resolve_generation_start_state`、`initial_generation_loop_state`、
`process_single_chapter`:resume 锚点推导、`skip_write_edit`、attempt 递归上限全在这三者
里面,假造它们就等于把要测的东西换成了假的。

## 工作流引擎

「工作流」是可增删的一等实体,不再只有长/短两行。`pipeline_configs` 一行 = 一个工作流:

- `graph` (JSON) —— 单章生成的**拓扑**:步骤 + 裁决边 + 预算。为空时由
  `services/chapter_graph.default_graph()` 构造,**代码是默认拓扑的权威**。
- `surface_strategy` —— `frozen_v43` / `short_form` / `custom`,决定代码注入表面。
- `prompt_category` —— 指向别的工作流即「共享它的提示词」。
- `policy` / `stages` / `nodes` —— 策略开关与阶段列表(后两者仍驱动 `PipelineStep` 顺序)。

`workflow_nodes` 是可复用的**节点库**:一个节点 = 角色 + 提示词 + 名称。**执行器由角色
推导**(`chapter_graph.ROLE_AGENT`),不是用户输入 —— 角色决定跑哪个适配器,而适配器调哪个
agent 的哪个方法是写死的 Python。凭空造一种新程序行为需要写代码。

11 个角色(`chapter_graph.GRAPH_ROLES`),适配器在 `worker_support/chapter_steps.py`。
其中 `context_refresh` 与 `publish` 是**系统角色**:没有提示词、不可删。
裁决词表固定为 `ok`/`rewrite`/`fail`/`blocked`/`empty`/`skipped`,前端不可扩展。

两条硬规则:

- **`disabled_when` 挂在边上而不是预算上**。同一个 rewrite 预算,进入 write-edit 簇的
  入口边不看 `enable_editor_loop`,回边看。搞反了该开关一关连初稿都不写。
- **无守卫的环在写入时静态拒绝**(DFS 三色标记),运行时另有 200 步上限兜住预算写错
  导致的不收敛。

提示词覆盖的唯一接缝是 `services/prompt_scope.py`(contextvar),只在
`agents/base.AgentBase.get_prompt_template` 解析**一次** —— 套两次在病态映射下会翻回去。
逐步骤生效,所以三个共用 `validator_validate_content` 的 validator 角色互不牵连。

`quality_dims` **不可自由设置**:Editor 的输出 schema 是固定 pydantic 模型,自定义维度
不会被 LLM 产出,`quality_evaluation` 会永远 `complete=false`。API 直接拒绝。

## 架构

```
main.py (FastAPI)  ──┬── routers/          13 个,92 条路由(91 HTTP + 1 WebSocket)
                     └── services/         业务逻辑,PostgreSQL 唯一权威
worker_support/   任务编排:orchestrator 是 worker 循环唯一装配点
    ├── worker.py ─┘   外部模式薄壳(默认不用;API lifespan 内嵌同一套循环)
    └── agents/pipeline.py
        Planner → Writer → Editor → Validator → Extractor
core/                         中立词汇层:agent 名/流水线枚举/记忆与角色常量。
                              依赖图的叶子(只许 import 标准库);models 与
                              services 都从这里向下引用,禁止反向依赖 services
research/                     78 个实验版本(生产不导入)
```

词汇与调参的落点:`core/` 只放跨层词汇;agent 注册表在 `agents/agent_registry.py`,
数值调参在 `agents/tuning.py`(两者经 `agents/constants.py` facade 再导出);
per-agent 召回预算统一在 `services/novel_memory_recall.AGENT_RECALL_PROFILES`
单表;前端事件名与 extractor 阶段文案在 `services/stream_events.py`。
`services/experiment_recorder/` 是包(io/context/events/manifest/publication),
`services/experiment_recorder.__init__` 再导出完整公共面。

**流水线**:`agents/pipeline.py` 用 `@register_node` 注册五个节点,各节点靠 `_fork()` 浅拷贝 context 避免污染共享状态。单章的**编排**由图解释器驱动(见上),而不是硬编码的顺序。新增 Job 类型只需在 `worker_support/orchestrator.py:JOB_HANDLERS` 注册 handler。

**Job 队列**:`claim_pending_jobs` 用 `with_for_update(skip_locked=True)` 做多 worker 安全抢占。向量同步走 VectorOutbox 最终一致。

**内嵌 / 独立 worker**:`DISABLE_IN_PROCESS_WORKER=false`(默认)单进程 —— API lifespan 经 `worker_support.orchestrator.bootstrap_worker_context` + `start_worker_loops` 内嵌 worker 三循环。`true` 时 worker 独立进程(worker.py 薄壳,`start_worker.bat` 显式入口)。注意 `main.py` 只在内嵌模式下重置 RUNNING job —— 否则 `uvicorn --reload` 会误杀外部 worker 的任务;也**不要** `from worker import ...`(会触发 IS_WORKER 污染与重复日志配置)。

## 权威模型

LLM **只能产出候选**,永远不能覆盖 canonical。渲染提示词或写记忆时必须守住:

- `published` / `user` / `frozen` / `accepted` —— 才是事实,可直接使用
- `candidate` / `generated` —— 只是待核对线索,不能确认身份、因果、生死、地点归属或物品状态
- `unknown` —— 可以描写观察、疑问、调查,**禁止补全结论**

`CharacterCard` 是人物写作的唯一可编辑事实源。AI 建卡与用户编辑走同一套事务:覆盖当前卡、存修改前快照、写修改记录、同步结构化关系、刷新只读 `CharacterManifest`。人物志不允许直接编辑。

## 分层记忆 L0–L3

PostgreSQL 是唯一业务数据源,ChromaDB 只是**可重建的向量投影**(丢失后重放 `VectorOutbox` 即可)。

- **L0** `novel_memory_evidence` —— 章节正文与 Extractor 原始结果,只追加
- **L1** `novel_memory_atoms` —— 结构化事实候选,带 Evidence、有效章节范围、置信度、版本、状态、权威等级
- **L2** `novel_scene_blocks` —— 按剧情线/卷/角色弧的压缩摘要
- **L3** `project_doctrines` —— 稳定创作契约与风格原则,不存一次性剧情事实

全部按 `project_id + branch_id + storyline_id` 隔离(主线 `branch_id IS NULL`、`storyline_id=main`)。写入用内容哈希 + `ON CONFLICT DO NOTHING`,重复 worker 执行不会覆盖正文或人工修改。

Recall 失败返回空记忆,主流程继续用既有 canonical context —— 不要把它改成抛异常。

细节见 `docs/novel-memory.md`。

## 提示词模板

`prompts/{extraction,planning,validation,writing}/{long_webnovel,zhihu_short}.json`。启动时种子到数据库 `prompt_templates` 表,**数据库是运行时权威来源**,可在「系统配置」页在线编辑、新建、删除。

磁盘 JSON 只补缺失行(`overwrite_existing=False`),不覆盖任何在线编辑。自定义工作流的
提示词由 `pipeline_configs.prompt_category` 路由,可以复制一套也可以共享别人的那套。

提示词缓存的跨进程新鲜度由**组合版本戳**保证(`services/config_versions.py` 的
`(COUNT(*), MAX(updated_at))`,依赖 prompt_templates.updated_at 列):任何进程改库,
独立 worker 的下一个 agent 步骤立即读到新提示词,无需重启。TTL 300 秒只在戳查询
不可用(DB 抖动/迁移未跑)时兜底。运行参数同理走 runtime_tunables 表+版本戳,
「系统配置 → 运行参数」页可改;worker 控制面在「系统配置 → 运行时」页。
