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
from routers import (
    chapters,
    characters,
    character_branches,
    knowledge_views,
    novel_memory,
    pipeline,
    projects,
    settings as settings_router,
    stream,
    system_configs,
    worker_admin,
)
from services.stream_manager import stream_manager
from services.storage_authority import storage_health_report, storage_consistency_report
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from services.access_control import require_local_request
from services.service_errors import ServiceError
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
    # worker 启动引导与外部 worker.py 共用（orchestrator 是唯一装配点）：
    # init_db + tokenizer/chroma 预热 + workflow_registry 刷新。
    from worker_support.orchestrator import bootstrap_worker_context, start_worker_loops

    await bootstrap_worker_context()

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
        from services.startup_recovery import reset_stale_running_jobs

        await reset_stale_running_jobs()
    else:
        logger.info("startup_job_recovery_skipped external_worker=true")

    # Start worker loops as background tasks inside the FastAPI event loop.
    # 注意：不能 `from worker import ...` —— 那会触发 worker.py 的模块级副作用
    # （mark_worker_process 把本 API 进程的 IS_WORKER 污染为 "1"、重复
    # configure_logging）。装配点在 worker_support.orchestrator。
    if not external_worker:
        for name, task in start_worker_loops().items():
            setattr(app.state, name, task)
    else:
        logger.info("in_process_worker_disabled")

    # Security warning: STREAM_INTERNAL_TOKEN should be set in production.
    if not app_config.STREAM_INTERNAL_TOKEN:
        logger.warning("stream_internal_token_missing localhost_only=true")
    if app_config.ALLOW_REMOTE_ACCESS and not app_config.REMOTE_ACCESS_TOKEN:
        logger.warning("remote_access_token_missing remote_requests_denied=true")

    # 生产提示词版本已冻结；改 .env 里的版本号不会生效，必须显式提示。
    from config import warn_if_prompt_version_overridden
    prompt_version_warning = warn_if_prompt_version_overridden()
    if prompt_version_warning:
        logger.warning("prompt_version_override_ineffective %s", prompt_version_warning)

    yield
    # Shutdown: 先停轮询循环与在跑的 job 任务并等待收尾，再关共享 client。
    # 顺序反了的话，残余广播协程会重建一个永不关闭的 http client。
    shutdown_tasks = []
    for attr in ("jobs_task", "vector_task", "orphan_cleanup_task"):
        if hasattr(app.state, attr):
            task = getattr(app.state, attr)
            task.cancel()
            shutdown_tasks.append(task)

    from worker_support.task_registry import cancel_all_and_wait
    await cancel_all_and_wait()

    if shutdown_tasks:
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)

    from services.shared_http import close_shared_client
    from services.stream_manager import close_stream_http_client
    await close_shared_client()
    await close_stream_http_client()


app = FastAPI(title="Novel Assistant", lifespan=lifespan)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.middleware("http")
async def local_access_guard(request: Request, call_next):
    token = begin_request_context(request.headers.get("X-Request-ID"))
    try:
        if request.url.path not in {"/health"}:
            try:
                require_local_request(request)
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
                response.headers["X-Request-ID"] = request_id_var.get()
                return response
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
app.include_router(characters.router, prefix="/api/writing", tags=["characters"])
app.include_router(character_branches.router, prefix="/api/writing", tags=["character-branches"])
app.include_router(knowledge_views.router, prefix="/api/writing", tags=["knowledge"])
app.include_router(novel_memory.router, prefix="/api/writing", tags=["novel-memory"])
app.include_router(settings_router.router, prefix="/api", tags=["settings"])
app.include_router(stream.router, prefix="/api/writing", tags=["stream"])
app.include_router(system_configs.router, prefix="/api/system-configs", tags=["system-configs"])
app.include_router(worker_admin.router, prefix="/api/worker", tags=["worker"])


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
    await stream_manager.deliver_local(req.project_id, req.event_type, req.data)
    return {"ok": True}

from fastapi.staticfiles import StaticFiles

FRONTEND_PATH = Path(app_config.FRONTEND_DIR) / "index.html"

# Mount static assets. check_dir=False：frontend/dist 被 gitignore，纯后端
# 部署/新克隆时目录不存在不能让 import main 直接崩。
app.mount("/assets", StaticFiles(directory=Path(app_config.FRONTEND_DIR) / "assets", check_dir=False), name="assets")


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
