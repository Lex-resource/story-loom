# 数据库运行说明

## 唯一数据库

Novel Assistant 只使用 PostgreSQL。应用、worker 和 Alembic 共同读取 `.env` 中同一个 `DATABASE_URL`，连接串必须使用 `postgresql+asyncpg://`。

不支持 SQLite 或第二套业务数据库。仓库中的 SQLite 文件属于已归档的历史空文件，不参与运行。

## 启动顺序

- `start_all.bat`：先执行一次 Alembic migration，成功后再启动 API、独立 worker 和前端。
- `start_backend.bat`：单独启动 API 时先执行 migration。
- `start_worker.bat`：worker 不修改结构，只在入口校验数据库 revision 已到 head。
- `python scripts/migrate_db.py`：手动把当前 PostgreSQL 升级到唯一 Alembic head。

Migration 失败时服务不会继续启动。禁止恢复启动时 `Base.metadata.create_all()` 或手写 `ALTER TABLE` 补列。

## 日常检查

```powershell
C:\Users\33694\anaconda3\envs\xiaoshuo\python.exe -m alembic current
C:\Users\33694\anaconda3\envs\xiaoshuo\python.exe -m alembic heads
C:\Users\33694\anaconda3\envs\xiaoshuo\python.exe -m alembic check
C:\Users\33694\anaconda3\envs\xiaoshuo\python.exe scripts\migrate_db.py
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
