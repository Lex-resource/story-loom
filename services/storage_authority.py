"""Storage authority and recovery contract for the application.

The database owns structured application state. Files are authoritative only
for the current Living Docs Markdown and runtime settings are owned by the
``SystemSettings`` row after legacy migration. ChromaDB is a rebuildable
projection fed by ``VectorOutbox`` and must never be treated as the source of
truth.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.pipeline_types import VectorOutboxStatus
from services.living_docs_files import checksum
from models.novel import LivingDocVersion, VectorOutbox
from services.vector_chroma import chroma_warmup_ok

@dataclass(frozen=True)
class StorageAuthority:
    name: str
    role: str
    source_of_truth: bool
    recovery: str

STORAGE_AUTHORITIES = (
    StorageAuthority(
        "postgresql",
        "projects, chapters, jobs, structured knowledge, prompts, settings, versions and usage",
        True,
        "Restore PostgreSQL first; run Alembic migrations before starting workers.",
    ),
    StorageAuthority(
        "living_docs_outline_files",
        "raw global/act outline Markdown",
        True,
        "Restore outline files from version snapshots or regenerate them from Novel.outline.",
    ),
    StorageAuthority(
        "system_settings_legacy_file",
        "pre-database settings import only",
        False,
        "Read once when SystemSettings is absent, then remove the legacy file.",
    ),
    StorageAuthority(
        "living_docs_projection_files",
        "generated knowledge Markdown, graph JSON and snapshots",
        False,
        "Rebuild from PostgreSQL SettingsDoc rows and LivingDocVersion records.",
    ),
    StorageAuthority(
        "chromadb",
        "vector search projection",
        False,
        "Replay pending VectorOutbox rows and rebuild the index if necessary.",
    ),
)

def storage_health_report() -> dict:
    roots = {
        "living_docs": Path(settings.LIVING_DOCS_DIR),
        "chroma": Path(settings.CHROMA_PERSIST_DIR),
        "settings_parent": Path(settings.SETTINGS_FILE).parent,
    }
    checks = {}
    for name, path in roots.items():
        parent = path if path.exists() else path.parent
        checks[name] = {
            "path": str(path),
            "exists": path.exists(),
            "parent_exists": parent.exists(),
            "writable": bool(parent.exists() and os.access(parent, os.W_OK)),
        }
    # chroma 启动预热健康标志（services/vector_chroma.preload_chroma 写入）：
    # unknown=未预热（预热关闭或尚未跑到），failed=读写探针失败 —— chroma 仍
    # 可用但召回走"异常→空记忆"降级，应查启动日志。
    warmup = "ok" if chroma_warmup_ok else ("unknown" if chroma_warmup_ok is None else "failed")

    return {
        "authorities": [authority.__dict__ for authority in STORAGE_AUTHORITIES],
        "checks": checks,
        "chroma_warmup": warmup,
    }

async def storage_consistency_report(db: AsyncSession) -> dict:
    status_rows = await db.execute(
        select(VectorOutbox.status, func.count(VectorOutbox.id)).group_by(VectorOutbox.status)
    )
    outbox_counts = {
        getattr(status, "value", status): int(count)
        for status, count in status_rows.all()
    }

    version_rows = await db.execute(
        select(LivingDocVersion)
        .order_by(LivingDocVersion.created_at.desc())
        .limit(200)
    )
    missing_files: list[str] = []
    checksum_mismatches: list[str] = []
    versions = version_rows.scalars().all()
    for version in versions:
        path = Path(version.path)
        if not path.exists():
            missing_files.append(str(path))
            continue
        if version.checksum:
            actual = checksum(path.read_text(encoding="utf-8"))
            if actual != version.checksum:
                checksum_mismatches.append(str(path))

    failed = outbox_counts.get(VectorOutboxStatus.FAILED.value, 0)
    return {
        "status": "degraded" if failed or missing_files or checksum_mismatches else "ok",
        "vector_outbox": outbox_counts,
        "living_doc_versions_checked": len(versions),
        "missing_version_files": missing_files,
        "checksum_mismatches": checksum_mismatches,
    }
