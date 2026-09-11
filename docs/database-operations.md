# 数据库运行说明

## 唯一数据库

Novel Assistant 只使用 PostgreSQL。应用、worker 和 Alembic 共同读取 `.env` 中同一个 `DATABASE_URL`，连接串必须使用 `postgresql+asyncpg://`。

不支持 SQLite 或第二套业务数据库。仓库中的 SQLite 文件属于已归档的历史空文件，不参与运行。

## 启动顺序

- `start_all.bat`：先执行一次 Alembic migration，成功后再启动 API（默认内嵌 worker）和前端。
- `start_backend.bat`：单独启动 API 时先执行 migration。
- `start_worker.bat`：独立 worker 的显式入口（外部模式，`DISABLE_IN_PROCESS_WORKER=true` 时使用）；不修改结构，只在入口校验数据库 revision 已到 head。
- `python scripts/migrate_db.py`：手动把当前 PostgreSQL 升级到唯一 Alembic head。

Migration 失败时服务不会继续启动。禁止恢复启动时 `Base.metadata.create_all()` 或手写 `ALTER TABLE` 补列。

## 角色卡迁移

角色卡域使用以下 PostgreSQL 表：`character_cards`、`character_card_snapshots`、`character_card_change_records`、`character_chapter_states`、`character_relationships`、`character_arcs`、`character_manifests`、`character_branches` 和 `character_branch_chapters`。

角色卡表结构由标准 Alembic 迁移建表，升级到包含角色卡的 head 即完成建表，**没有**额外的数据迁移脚本（早期文档提到的 `scripts/migrate_character_cards.py` 从未落地）。角色卡内容由角色卡页编辑或 AI 建卡生成；旧 `settings_docs` 人物志保留原样不自动转换。

数据权威关系如下：角色卡是唯一可编辑事实源；人物志由数据库中的角色卡、章节状态和关系表确定性生成并持久化，接口只读；章节状态只保存角色状态发生变化的章节。不要直接更新 `character_manifests` 或通过 `character_state` 活文档写入角色信息。

角色支线在创建时冻结主线锚点上下文，支线状态和正文只写入支线表。支线不更新 `chapters`、`character_cards`、`character_chapter_states`、`character_relationships` 或主线统计；删除项目时由外键级联删除支线数据。支线章节通过 `VectorOutbox` 投影到以支线 ID 命名的独立向量集合，主线检索不读取该集合，归档时清理集合。`character_branch_auto_discovery_enabled` 默认关闭，开启后只允许候选发现，不自动生成正文。

Prompt 模板运行时以 PostgreSQL `prompt_templates` 为权威来源。源码 JSON 只负责缺失模板的种子，不能覆盖用户在系统配置页面的编辑；更新内置 Prompt 后，现有数据库需要通过系统配置或定向数据迁移显式同步。

## 日常检查

```powershell
python -m alembic current
python -m alembic heads
python -m alembic check
python scripts\migrate_db.py
```

`current` 与 `heads` 应指向相同的唯一 revision，`check` 应输出 `No new upgrade operations detected.`。迁移脚本会自动执行这项漂移检查。

## 测试数据库

迁移链集成测试只接受 `TEST_DATABASE_URL`，并强制数据库名称包含 `test`。它必须指向可清空或可重建的独立 PostgreSQL 测试库，不能指向日常业务数据库。

未配置测试库时，迁移链集成测试安全跳过；其余单元测试不需要第二种数据库。

## 备份和失败处理

执行生产数据迁移前使用 `pg_dump` 备份。升级失败时保留错误日志和备份，不自动执行 `alembic downgrade`；先修复 migration，再重新执行同一升级命令。
## Storage consistency and projection repair

Run `python scripts/reconcile_storage.py` for a read-only consistency report.
Run `python scripts/reconcile_storage.py --repair` to explicitly reset failed or expired
VectorOutbox leases and replay all pending vector projection work. Missing or checksum-mismatched
Living Docs version files are reported but never silently recreated.
