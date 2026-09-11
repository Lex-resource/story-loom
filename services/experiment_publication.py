"""Close experiment metrics when a chapter reaches published state."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from services.experiment_recorder import arecord_published_chapter
from services.pipeline_commands import experiment_params_for_project


logger = logging.getLogger(__name__)


async def record_published_chapter_for_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    chapter_index: int,
    *,
    publication_source: str,
) -> bool:
    experiment = await experiment_params_for_project(db, project_id)
    if not experiment:
        return False
    try:
        return await arecord_published_chapter(
            experiment,
            project_id=project_id,
            chapter_index=chapter_index,
            publication_source=publication_source,
        )
    except Exception:
        # Research recording must never turn a published chapter into a failed
        # production job.
        logger.exception(
            "experiment_publication_record_failed project_id=%s chapter_index=%s",
            project_id,
            chapter_index,
        )
        return False
