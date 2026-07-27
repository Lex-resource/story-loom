import os
import logging
from config import apply_runtime_env
apply_runtime_env()
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel, Field
from database import init_db
from routers import (
    chapters,
    issues,
    knowledge,
    knowledge_views,
    living_docs,
    pipeline,
    projects,
    settings as settings_router,
    stream,
    system_configs,
)
from services.stream_manager import stream_manager
from services.storage_authority import storage_health_report, storage_consistency_report
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from services.access_control import require_local_request
from services.logging_config import configure_logging, begin_request_context, end_request_context, request_id_var
from config import settings as app_config
import asyncio

configure_logging()
logger = logging.getLogger(__name__)


class InternalBroadcastRequest(BaseModel):
    project_id: str
    event_type: str
    data: dict = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    try:
        from database import async_session
        from services.prompt_loader import seed_prompts_to_database
        async with async_session() as session:
            await seed_prompts_to_database(session)
    except Exception:
        logger.exception("prompt_seed_failed")

    try:
        from database import async_session
        from sqlalchemy import select
        from models.novel import PromptTemplate
        from services.prompt_loader import REQUIRED_PROMPT_TEMPLATES
        async with async_session() as session:
            for name, cat in REQUIRED_PROMPT_TEMPLATES:
                res = await session.execute(select(PromptTemplate).where(
                    PromptTemplate.name == name, PromptTemplate.category == cat
                ))
                if not res.scalars().first():
                    logger.warning("required_prompt_missing name=%s category=%s", name, cat)
    except Exception:
        logger.exception("required_prompt_check_failed")

    from config import settings as app_config
    external_worker = app_config.DISABLE_IN_PROCESS_WORKER.lower() == "true"

    # Only reset stuck jobs when the in-process worker owns them.
    # With an external worker, uvicorn --reload must not mark running jobs failed.
    if not external_worker:
        from sqlalchemy import update
        from models.novel import Job, Novel
        from services.pipeline_state import JobStatus, NovelStatus
        from database import async_session
        try:
            from sqlalchemy import select
            from services.job_payload import append_job_error
            async with async_session() as session:
                res_jobs = await session.execute(select(Job).where(Job.status == JobStatus.RUNNING))
                running_jobs = res_jobs.scalars().all()
                for job in running_jobs:
                    job.status = JobStatus.FAILED
                    append_job_error(job, "服务器在执行中意外重启或中断")

                await session.execute(
                    update(Novel).where(Novel.status == NovelStatus.GENERATING).values(status=NovelStatus.PAUSED)
                )
                await session.commit()
                logger.info("startup_job_recovery_completed jobs=%s", len(running_jobs))
        except Exception:
            logger.exception("startup_job_recovery_failed")
    else:
        logger.info("startup_job_recovery_skipped external_worker=true")

    # Start worker loops as background tasks inside the FastAPI event loop
    if not external_worker:
        from worker import poll_jobs, poll_vector_outbox
        app.state.jobs_task = asyncio.create_task(poll_jobs())
        app.state.vector_task = asyncio.create_task(poll_vector_outbox())
    else:
        logger.info("in_process_worker_disabled")

    # Security warning: STREAM_INTERNAL_TOKEN should be set in production.
    if not app_config.STREAM_INTERNAL_TOKEN:
        logger.warning("stream_internal_token_missing localhost_only=true")

    yield
    # Shutdown tasks on stop
    if hasattr(app.state, "jobs_task"):
        app.state.jobs_task.cancel()
    if hasattr(app.state, "vector_task"):
        app.state.vector_task.cancel()
    from services.stream_manager import close_stream_http_client
    await close_stream_http_client()


app = FastAPI(title="Novel Assistant", lifespan=lifespan)


@app.middleware("http")
async def local_access_guard(request: Request, call_next):
    token = begin_request_context(request.headers.get("X-Request-ID"))
    try:
        if request.url.path not in {"/health"}:
            require_local_request(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id_var.get()
        return response
    finally:
        end_request_context(token)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for uncaught exceptions in routes.

    Logs the error with request context and returns a uniform JSON 500
    response. In DEBUG mode the response includes the traceback to aid
    development; in production only a generic message is exposed to avoid
    leaking internal details.
    """
    logger.exception("Unhandled exception method=%s path=%s", request.method, request.url.path)
    detail = (
        f"{type(exc).__name__}: {exc}" if app_config.DEBUG else "Internal Server Error"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "type": type(exc).__name__},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in app_config.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/writing", tags=["projects"])
app.include_router(pipeline.router, prefix="/api/writing", tags=["pipeline"])
app.include_router(chapters.router, prefix="/api/writing", tags=["chapters"])
app.include_router(issues.router, prefix="/api/writing", tags=["issues"])
app.include_router(knowledge_views.router, prefix="/api/writing", tags=["knowledge"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(living_docs.router, prefix="/api/writing", tags=["living-docs"])
app.include_router(settings_router.router, prefix="/api", tags=["settings"])
app.include_router(stream.router, prefix="/api/writing", tags=["stream"])
app.include_router(system_configs.router, prefix="/api/system-configs", tags=["system-configs"])


@app.post("/api/internal/broadcast")
async def internal_broadcast(req: InternalBroadcastRequest, request: Request):
    configured_token = app_config.STREAM_INTERNAL_TOKEN
    token = request.headers.get("X-Internal-Token", "")
    client_host = request.client.host if request.client else ""
    is_localhost = client_host in ("127.0.0.1", "::1", "localhost")

    # Auth logic:
    # - If STREAM_INTERNAL_TOKEN is configured: require matching token OR localhost.
    # - If empty (default): localhost-only (token-based auth is disabled).
    # An empty configured_token must NOT match an empty header to prevent bypass.
    if configured_token and token == configured_token:
        pass
    elif is_localhost:
        pass
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    await stream_manager._deliver(req.project_id, req.event_type, req.data)
    return {"ok": True}

from fastapi.staticfiles import StaticFiles

FRONTEND_PATH = Path(app_config.FRONTEND_DIR) / "index.html"

# Mount static assets
app.mount("/assets", StaticFiles(directory=Path(app_config.FRONTEND_DIR) / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
async def root():
    if FRONTEND_PATH.exists():
        return FRONTEND_PATH.read_text(encoding="utf-8")
    fallback_path = Path(__file__).parent / "frontend" / "index.html"
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8")
    return HTMLResponse("前端未构建。请运行 npm run build。", status_code=404)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/storage")
async def storage_health(db: AsyncSession = Depends(get_db)):
    report = storage_health_report()
    report["consistency"] = await storage_consistency_report(db)
    return report
