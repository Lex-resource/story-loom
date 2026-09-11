"""Filesystem helpers for living docs."""
import hashlib
import json
from pathlib import Path
from typing import Optional

from config import settings
from services.novel_constants import CHAPTER_VERSION_DIR_TEMPLATE


import logging

logger = logging.getLogger(__name__)


DOCS_DIR = Path(settings.LIVING_DOCS_DIR)


def get_project_dir(project_id: str) -> Path:
    return DOCS_DIR / project_id


def get_current_dir(project_id: str) -> Path:
    return get_project_dir(project_id) / "current"


def get_versions_dir(project_id: str) -> Path:
    return get_project_dir(project_id) / "versions"


def get_archive_dir(project_id: str) -> Path:
    return get_project_dir(project_id) / "archive"


def file_path(project_id: str, doc_type: str) -> Path:
    return get_current_dir(project_id) / f"{doc_type}.md"


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def read_current_doc(project_id: str, doc_type: str) -> Optional[str]:
    path = file_path(project_id, doc_type)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def write_current_doc(project_id: str, doc_type: str, content: str) -> None:
    write_text_atomic(file_path(project_id, doc_type), content)


def snapshot_current_doc(project_id: str, chapter_index: int, doc_type: str, content: str) -> str:
    chapter_dir = get_versions_dir(project_id) / CHAPTER_VERSION_DIR_TEMPLATE.format(chapter_index)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    dst = chapter_dir / f"{doc_type}.md"
    dst.write_text(content, encoding="utf-8")
    return checksum(content)


def archive_doc(project_id: str, doc_type: str, filename: str) -> None:
    content = read_current_doc(project_id, doc_type)
    if content is None:
        return
    archive_dir = get_archive_dir(project_id)
    archive_dir.mkdir(parents=True, exist_ok=True)
    dst = archive_dir / filename
    dst.write_text(content, encoding="utf-8")


def read_graph(project_id: str) -> Optional[dict]:
    path = get_current_dir(project_id) / "character_graph.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[LivingDocs WARN] Failed to parse graph JSON for {project_id}: {exc}")
        return None


def write_graph(project_id: str, graph_data: dict) -> None:
    current_dir = get_current_dir(project_id)
    current_dir.mkdir(parents=True, exist_ok=True)
    path = current_dir / "character_graph.json"
    path.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_graph(project_id: str) -> None:
    path = get_current_dir(project_id) / "character_graph.json"
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            logger.warning(f"[LivingDocs WARN] Failed to delete graph for {project_id}: {exc}")
