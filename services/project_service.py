from services.job_payload import get_blocking_job_error_message, get_job_params
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.novel import Chapter, Job, Novel, PromptTemplate
from services.project_stats import sum_project_chars
from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL, AGENT_PLANNER
from services.novel_constants import (
    API_STATUS_DELETED,
    DEFAULT_CHAPTER_INDEX,
    DEFAULT_OPTIMIZE_INTERVAL,
    DEFAULT_TARGET_CHAPTERS,
    DEFAULT_WORD_COUNT_PER_CHAPTER,
    JOB_TYPE_GENERATE,
    NOVEL_MODE_AUTO,
    NOVEL_MODE_STEP,
    NOVEL_TYPE_PROJECT,
)
from services.pipeline_types import JobStatus, NovelStatus
from services.creative_profile import normalize_creative_profile, workflow_format_for_profile
from services.ids import parse_project_id


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    novel_format: str | None = Field(default=None, max_length=100)
    creative_profile: dict | None = None
    target_chapters: int | None = Field(default=None, ge=1, le=10_000)
    word_count_per_chapter: int | None = Field(default=None, ge=1, le=100_000)
    optimize_interval: int = Field(default=DEFAULT_OPTIMIZE_INTERVAL, ge=1, le=10_000)
    mode: str = Field(default=NOVEL_MODE_STEP, pattern=f"^({NOVEL_MODE_STEP}|{NOVEL_MODE_AUTO})$")
    user_prompt: str | None = Field(default=None, max_length=100_000)
    prompt: str | None = Field(default=None, max_length=100_000)
    reference_style: str = Field(default="", max_length=100_000)

    @model_validator(mode="after")
    def validate_required_text(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        prompt = (self.user_prompt or self.prompt or "").strip()
        if not prompt:
            raise ValueError("user_prompt must not be blank")
        self.user_prompt = prompt
        return self

async def get_formats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PromptTemplate.category).where(PromptTemplate.category.isnot(None)).distinct())
    formats = result.scalars().all()
    # Provide a fallback default if table is empty
    if not formats:
        formats = [NOVEL_FORMAT_LONG_WEBNOVEL]
    return {"formats": [f for f in formats if f]}

async def list_projects(db: AsyncSession = Depends(get_db)):
    # Single query with left join aggregates to avoid N+1 per-novel sub-queries.
    from sqlalchemy import func as sa_func
    chapter_count = sa_func.count(Chapter.id).label("chapter_count")
    char_sum = sa_func.coalesce(sa_func.sum(Chapter.word_count), 0).label("total_chars")
    result = await db.execute(
        select(Novel, chapter_count, char_sum)
        .outerjoin(Chapter, Chapter.novel_id == Novel.id)
        .where(Novel.type == NOVEL_TYPE_PROJECT)
        .group_by(Novel.id)
        .order_by(Novel.created_at.desc())
    )
    rows = result.all()
    ret = []
    for novel, written_count, total_chars in rows:
        ret.append({
            "id": str(novel.id),
            "title": novel.title,
            "status": novel.status,
            "novel_format": novel.novel_format,
            "creative_profile": normalize_creative_profile(
                novel.creative_profile,
                novel_format=novel.novel_format,
                target_chapters=novel.target_chapters,
                word_count_per_chapter=novel.word_count_per_chapter,
            ),
            "current_chapter": written_count,
            "target_chapters": novel.target_chapters,
            "total_chars": total_chars,
            "created_at": novel.created_at.isoformat() if novel.created_at else None,
            "updated_at": novel.updated_at.isoformat() if novel.updated_at else None,
        })
    return ret


async def create_project(data: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    from models.novel import Job

    payload = data.model_dump()

    creative_profile = normalize_creative_profile(
        payload.get("creative_profile"),
        novel_format=payload.get("novel_format"),
        target_chapters=payload.get("target_chapters"),
        word_count_per_chapter=payload.get("word_count_per_chapter"),
    )
    novel_format = workflow_format_for_profile(creative_profile)
    novel = Novel(
        title=data.title.strip(),
        author=data.author,
        type=NOVEL_TYPE_PROJECT,
        novel_format=novel_format,
        creative_profile=creative_profile,
        target_chapters=creative_profile["target_chapters"],
        word_count_per_chapter=creative_profile["word_count_per_chapter"],
        optimize_interval=data.optimize_interval,
        mode=data.mode,
        status=NovelStatus.GENERATING,
    )
    db.add(novel)
    await db.flush()

    job_params = {
        "user_prompt": data.user_prompt,
        "reference_style": data.reference_style,
        "creative_profile": creative_profile,
        "bootstrap_skeleton": True,
    }
    if data.mode == NOVEL_MODE_AUTO:
        job_params["batch_size"] = creative_profile["target_chapters"]

    job = Job(
        project_id=novel.id,
        type=JOB_TYPE_GENERATE,
        status=JobStatus.PENDING,
        current_step=AGENT_PLANNER,
        current_chapter=DEFAULT_CHAPTER_INDEX,
        params=job_params,
    )
    db.add(job)
    await db.commit()
    return {"project_id": str(novel.id), "status": novel.status, "job_id": str(job.id)}


async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).where(Novel.id == parse_project_id(project_id)))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(novel)
    await db.commit()
    return {"status": API_STATUS_DELETED}


async def get_status(project_id: str, db: AsyncSession = Depends(get_db)):
    novel = await get_novel_or_404(db, project_id)

    job_result = await db.execute(
        select(Job).where(Job.project_id == novel.id).order_by(Job.created_at.desc()).limit(1)
    )
    job = job_result.scalar_one_or_none()
    count_res = await db.execute(select(func.count()).select_from(Chapter).where(Chapter.novel_id == novel.id))
    written_count = int(count_res.scalar() or 0)
    total_chars = await sum_project_chars(db, novel.id)

    job_error = get_blocking_job_error_message(job) if job else None
    job_params = get_job_params(job) if job else {}

    return {
        "project_id": str(novel.id),
        "title": novel.title,
        "status": novel.status,
        "mode": novel.mode,
        "word_count_per_chapter": novel.word_count_per_chapter,
        "novel_format": novel.novel_format,
        "creative_profile": normalize_creative_profile(
            novel.creative_profile,
            novel_format=novel.novel_format,
            target_chapters=novel.target_chapters,
            word_count_per_chapter=novel.word_count_per_chapter,
        ),
        "optimize_interval": novel.optimize_interval,
        "current_chapter": written_count,
        "target_chapters": novel.target_chapters,
        "total_chapters": written_count,
        "total_chars": total_chars,
        "latest_job_status": job.status if job else None,
        "latest_job_error": job_error,
        "latest_job_step": job.current_step if job and job.status in (JobStatus.RUNNING, JobStatus.PENDING, JobStatus.PAUSED) else None,
        "latest_job_chapter": job.current_chapter if job and job.status in (JobStatus.RUNNING, JobStatus.PENDING, JobStatus.PAUSED) else None,
        "await_outline_review": job_params.get("await_outline_review", False),
        "validation_failed_chapter": job_params.get("validation_failed_chapter"),
    }


async def get_jobs(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job).where(Job.project_id == parse_project_id(project_id)).order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    return [{"id": str(j.id), "type": j.type, "status": j.status, "current_step": j.current_step} for j in jobs]


async def get_novel_or_404(db: AsyncSession, project_id: str) -> Novel:
    """按 project_id 查询 Novel，不存在则抛 404。"""
    result = await db.execute(select(Novel).where(Novel.id == parse_project_id(project_id)))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Project not found")
    return novel
