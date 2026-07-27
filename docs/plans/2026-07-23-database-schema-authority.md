# Database Schema Authority Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Alembic 成为应用数据库结构的唯一生产级事实来源，移除启动时 `create_all()` 和手写补列造成的双轨迁移。

**Architecture:** 保留 SQLAlchemy `Base.metadata` 作为模型声明和测试夹具，所有真实数据库变更只通过 Alembic revision 完成。启动脚本先串行迁移，API 与 worker 启动时只校验 revision 是否处于 head，避免两个进程并发改表。

**Tech Stack:** Python 3.11+, SQLAlchemy asyncio, Alembic, PostgreSQL, asyncpg, pytest。应用、迁移和数据库集成测试统一使用 PostgreSQL。

---

## Decision And Boundaries

- 采用：显式迁移命令 + 运行时版本校验。
- 不采用：每次 API/worker 启动都自动迁移。两个进程同时启动时会产生 DDL 竞争，失败语义也不清晰。
- 不采用：保留 `create_all()` + Alembic 混合模式。它无法证明历史迁移链可用，也会掩盖漏写 revision。
- `Base.metadata.create_all()` 只允许出现在隔离的测试夹具中，不允许进入应用启动路径。
- 不支持 SQLite/MySQL 运行模式；`DATABASE_URL` 必须使用 `postgresql+asyncpg://`。
- 现有 `7f8c3e5d4a21` 已包含 `pipeline_step`、`settings_docs.data`、`jobs.params`，因此删除运行时补列前不需要再造重复 migration。

### Task 1: Lock The Current Migration Contract

**Files:**
- Create: `tests/database/test_migration_chain.py`
- Create: `tests/database/__init__.py`
- Inspect: `alembic/versions/*.py`

**Step 1: Write a failing blank-database migration test**

测试读取 `TEST_DATABASE_URL` 指向名字含 `test` 的一次性 PostgreSQL 数据库，执行 `upgrade head`，然后断言 `alembic_version` 等于唯一 head，并检查所有模型表及关键列。

**Step 2: Run the focused test**

Run: `python -m pytest tests/database/test_migration_chain.py -v`

Expected: 没有配置独立测试库时安全跳过；配置后必须从空 PostgreSQL 数据库升级成功。

**Step 3: Fill migration gaps without rewriting history**

对过去由 `create_all()` 隐式创建、但 revision 链缺失的表新增 head migration。不得修改已发布 revision id、down_revision 或字段含义。

**Step 4: Re-run the migration test**

Expected: PASS，并且空 PostgreSQL 数据库最终结构包含所有当前模型表。

**Step 5: Commit**

```bash
git add tests/database alembic/versions
git commit -m "test: verify database migration chain"
```

### Task 2: Make Alembic Use Runtime Configuration

**Files:**
- Modify: `alembic/env.py`
- Modify: `alembic.ini`
- Test: `tests/database/test_alembic_config.py`

**Step 1: Write a failing configuration test**

断言 Alembic 实际 URL 来自 `config.settings.DATABASE_URL`，而不是 `alembic.ini` 中硬编码的用户名和密码。

**Step 2: Set the URL before engine construction**

在 `alembic/env.py` 中导入应用 settings，并执行：

```python
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
```

删除 `alembic.ini` 中真实连接串，保留无凭据占位值及说明。

**Step 3: Verify offline and online configuration**

Run: `python -m pytest tests/database/test_alembic_config.py -v`

Expected: PASS，测试输出不得泄露数据库密码。

**Step 4: Commit**

```bash
git add alembic/env.py alembic.ini tests/database/test_alembic_config.py
git commit -m "fix: source alembic database url from settings"
```

### Task 3: Add Explicit Migration And Version Check Commands

**Files:**
- Create: `services/schema_version.py`
- Create: `scripts/migrate_db.py`
- Test: `tests/services/test_schema_version.py`

**Step 1: Write version-state tests**

覆盖 `current == head`、缺少 `alembic_version`、落后多个 revision、出现未知 revision 四种状态。错误信息必须给出 `python scripts/migrate_db.py` 修复命令。

**Step 2: Implement a read-only startup validator**

`assert_schema_current(engine)` 只读取数据库 revision 和 Alembic heads，不执行 DDL。缺表或版本不一致时抛出明确的 `SchemaVersionError`。

**Step 3: Implement the one-shot migration command**

`scripts/migrate_db.py` 调用 `alembic.command.upgrade(config, "head")`，成功打印最终 revision，失败返回非零退出码且不吞 traceback。

**Step 4: Verify commands**

Run: `python -m pytest tests/services/test_schema_version.py -v`

Expected: PASS。

Run: `python scripts/migrate_db.py`

Expected: 数据库升级到 head；重复运行无额外结构变化。

**Step 5: Commit**

```bash
git add services/schema_version.py scripts/migrate_db.py tests/services/test_schema_version.py
git commit -m "feat: add explicit database migration command"
```

### Task 4: Remove Runtime Schema Mutation

**Files:**
- Modify: `database.py:27`
- Modify: `main.py:20`
- Modify: `worker.py:20`
- Test: `tests/test_database_startup.py`

**Step 1: Write failing startup tests**

断言 API 和 worker 启动会校验 schema；断言 `database.py` 不再执行 `Base.metadata.create_all()`、`ALTER TABLE` 或 `_ensure_runtime_columns()`。

**Step 2: Replace `init_db()` behavior**

将应用启动路径改为调用 `assert_schema_current(engine)`。删除 `_ensure_runtime_columns` 与 `_add_column_if_missing`；测试夹具仍可直接调用 `Base.metadata.create_all()`。

**Step 3: Run startup and route smoke tests**

Run: `python -m pytest tests/test_database_startup.py tests/test_smoke_imports.py tests/routers/test_route_map.py -v`

Expected: PASS。

**Step 4: Commit**

```bash
git add database.py main.py worker.py tests/test_database_startup.py
git commit -m "refactor: make startup database checks read only"
```

### Task 5: Serialize Local Startup

**Files:**
- Modify: `start_backend.bat`
- Modify: `start_all.bat`
- Modify: `start_worker.bat`
- Create: `docs/database-operations.md`

**Step 1: Make backend startup migrate first**

`start_backend.bat` 先执行 `python scripts/migrate_db.py`，失败时立即退出；成功后再启动 Uvicorn。

**Step 2: Make all-services startup wait for backend health**

`start_all.bat` 启动 backend 后轮询 `/health`，成功后才启动独立 worker 和前端，避免 worker 在 migration 完成前访问表。

**Step 3: Keep worker mutation-free**

`start_worker.bat` 不执行 migration；worker 入口只做 schema head 校验。单独启动 worker 前必须先运行迁移命令。

**Step 4: Document rollback and backup**

文档写清升级前备份、`alembic current`、`alembic heads`、升级失败处理；生产数据禁止自动 downgrade。

**Step 5: Verify**

Run: `start_all.bat`

Expected: migration 只执行一次，backend 健康后 worker 才开始轮询。

### Task 6: Add Schema Drift Gate

**Files:**
- Create: `tests/database/test_model_migration_drift.py`
- Modify: project CI configuration when CI is introduced

**Step 1: Add a drift test**

在迁移后的临时数据库上运行 Alembic autogenerate comparison；若 `Base.metadata` 与 head 之间存在新增/删除操作则失败，并打印差异。

**Step 2: Run the database gate**

Run: `python -m pytest tests/database -v`

Expected: PASS，且无待生成 migration。

**Step 3: Run full backend verification**

Run: `python -m pytest -q`

Expected: 全部通过；依赖安装放在最终环境整理阶段处理。

## Acceptance Criteria

- 应用代码不再执行建表或补列 DDL。
- 空数据库可以从 revision 0 升级到唯一 head。
- API/worker 遇到旧 schema 时快速失败并给出迁移命令。
- 模型变化但没有 migration 时测试失败。
- 启动流程不会让 API 与 worker 并发执行 migration。
