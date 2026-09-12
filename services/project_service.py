import uuid

from services.job_payload import get_blocking_job_error_message, get_job_params
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Chapter, Job, Novel, PipelineConfigModel
from services.project_stats import sum_project_chars
from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL, AGENT_PLANNER
from services.novel_constants import (
    API_STATUS_DELETED,
    DEFAULT_CHAPTER_INDEX,
    DEFAULT_OPTIMIZE_INTERVAL,
    JOB_TYPE_GENERATE,
    NOVEL_MODE_AUTO,
    NOVEL_MODE_STEP,
    NOVEL_TYPE_PROJECT,
)
from services.pipeline_types import JobStatus, NovelStatus
from services import workflow_registry
from services.creative_profile import normalize_creative_profile, workflow_format_for_profile
from services.project_deletion import delete_project_data

DEFAULT_JOB_HISTORY_PAGE_SIZE = 200
MAX_JOB_HISTORY_PAGE_SIZE = 500
async def get_formats(db: AsyncSession):
    """可选的创作工作流列表。

    原实现是 `SELECT DISTINCT category FROM prompt_templates` —— 从提示词表**反推**
    格式。于是新建的工作流不会出现（它可能复用别人的 category），而共享提示词的两个
    工作流会被合并成一个。现在直接查 `pipeline_configs`，那才是工作流的权威来源。

    返回结构保持 `{"formats": [...]}` 以兼容既有前端，另外附一份带中文名与说明的
    `workflows`，供「选工作流」的界面直接用。
    """
    result = await db.execute(
        select(PipelineConfigModel).order_by(
            PipelineConfigModel.builtin.desc(), PipelineConfigModel.name
        )
    )
    rows = result.scalars().all()

    if not rows:
        return {
            "formats": [NOVEL_FORMAT_LONG_WEBNOVEL],
            "workflows": [
                {
                    "name": NOVEL_FORMAT_LONG_WEBNOVEL,
                    "name_zh": "长篇小说",
                    "description": None,
                    "builtin": True,
                }
            ],
        }

    return {
        "formats": [row.name for row in rows],
        "workflows": [
            {
                "name": row.name,
                "name_zh": row.name_zh or row.name,
                "description": getattr(row, "description", None),
                "builtin": bool(getattr(row, "builtin", False)),
            }
            for row in rows
        ],
    }

async def list_projects(db: AsyncSession):
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


async def _resolve_workflow(db: AsyncSession, requested: str | None) -> str | None:
    """校验显式指定的工作流；没指定则返回 ``None`` 交给旧的按篇幅派生。

    原实现无条件用 ``workflow_format_for_profile(creative_profile)`` 从「长篇/短篇」
    二选一派生，于是**前端传什么 novel_format 都被丢掉** —— 工作流可自定义之后，
    这会让「选了自定义工作流」变成一句空话：项目仍落在内置两行之一。

    但名字必须是库里真实存在的工作流：``get_pipeline_config`` 查不到会抛
    ``ValueError``，而它在 worker 的每章生成路径上 —— 让一个拼错的名字落进
    ``Novel.novel_format``，等于建了一个永远跑不动的项目。
    """
    name = (requested or "").strip()
    if not name:
        return None

    exists = (
        await db.execute(
            select(PipelineConfigModel.id).where(PipelineConfigModel.name == name)
        )
    ).scalar_one_or_none()
    if exists is None:
        raise ValueError(f"工作流 '{name}' 不存在，请在「系统配置」里先创建它。")
    # 顺手预热缓存：normalize_creative_profile 紧接着就要问它是不是短篇表面，
    # 而那是同步调用，拿不到 session。
    await workflow_registry.refresh(db)
    return name


async def create_project(db: AsyncSession, data: dict):
    from models.novel import Job

    payload = dict(data)

    requested_workflow = await _resolve_workflow(db, payload.get("novel_format"))
    creative_profile = normalize_creative_profile(
        payload.get("creative_profile"),
        novel_format=requested_workflow,
        target_chapters=payload.get("target_chapters"),
        word_count_per_chapter=payload.get("word_count_per_chapter"),
    )
    # 显式选了工作流就用它；没选则沿用旧行为，按篇幅在内置两行里二选一。
    novel_format = requested_workflow or workflow_format_for_profile(creative_profile)
    novel = Novel(
        title=str(data.get("title", "")).strip(),
        author=data.get("author"),
        type=NOVEL_TYPE_PROJECT,
        novel_format=novel_format,
        creative_profile=creative_profile,
        target_chapters=creative_profile["target_chapters"],
        word_count_per_chapter=creative_profile["word_count_per_chapter"],
        optimize_interval=data.get("optimize_interval", DEFAULT_OPTIMIZE_INTERVAL),
        mode=data.get("mode", NOVEL_MODE_STEP),
        status=NovelStatus.GENERATING,
    )
    db.add(novel)
    await db.flush()

    job_params = {
        "user_prompt": data.get("user_prompt") or data.get("prompt"),
        "reference_style": data.get("reference_style", ""),
        "creative_profile": creative_profile,
        "bootstrap_skeleton": True,
    }
    if data.get("experiment"):
        experiment = data["experiment"]
        job_params["experiment"] = experiment if isinstance(experiment, dict) else experiment.model_dump(exclude_none=True)
    if data.get("mode") == NOVEL_MODE_AUTO:
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


async def delete_project(db: AsyncSession, pid: uuid.UUID):
    result = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result.scalar_one_or_none()
    if not novel:
        raise LookupError("Project not found")
    cleanup_errors = await delete_project_data(db, pid)
    return {
        "status": API_STATUS_DELETED,
        "projection_cleanup_errors": cleanup_errors,
    }


async def active_project_job_ids_for_delete(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    from services.project_deletion import active_project_job_ids

    return await active_project_job_ids(db, project_id)


async def get_status(db: AsyncSession, project_id: uuid.UUID):
    novel = await get_novel_or_raise(db, project_id)

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


async def get_jobs(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = DEFAULT_JOB_HISTORY_PAGE_SIZE,
    offset: int = 0,
):
    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc(), Job.id.asc())
        .limit(limit)
        .offset(offset)
    )
    jobs = result.scalars().all()
    return [{"id": str(j.id), "type": j.type, "status": j.status, "current_step": j.current_step} for j in jobs]


async def get_novel_or_raise(db: AsyncSession, project_id: uuid.UUID) -> Novel:
    """按 project_id 查询 Novel，不存在则抛 LookupError。"""
    result = await db.execute(select(Novel).where(Novel.id == project_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise LookupError("Project not found")
    return novel
