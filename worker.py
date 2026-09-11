"""独立 worker 进程入口（外部模式，start_worker.bat）。

单进程部署（默认）不需要本文件 —— API 进程的 lifespan 经
worker_support.orchestrator 直接内嵌同样的三循环。这里只是外部模式的薄壳：
模块级副作用（IS_WORKER 标记、日志配置）只在外部进程里做，main.py 不再
import 本模块（那会把 API 进程污染成 worker）。
"""
import os
from services.logging_config import configure_logging
configure_logging()
from config import mark_worker_process
mark_worker_process()
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from worker_support.orchestrator import (  # noqa: E402,F401
    JobAbortedException,
    JobPausedException,
    bootstrap_worker_context,
    check_paused,
    poll_jobs,
    poll_vector_outbox,
    process_generate_job,
    process_job,
    process_single_chapter,
    start_worker_loops,
)
from worker_support.orphan_cleaner import (
    cleanup_orphaned_jobs,
    cleanup_orphaned_jobs_periodic,
)


async def main():
    import asyncio
    import logging
    from config import warn_if_prompt_version_overridden

    # 生产提示词版本已冻结；改 .env 里的版本号不会生效，必须显式提示。
    prompt_version_warning = warn_if_prompt_version_overridden()
    if prompt_version_warning:
        logging.getLogger(__name__).warning(
            "prompt_version_override_ineffective %s", prompt_version_warning
        )

    await bootstrap_worker_context()

    await cleanup_orphaned_jobs()
    # 周期孤儿清理必须与 poll 循环并行：长驻 worker 进程里卡死的 RUNNING 行
    # 只能靠它回收（启动时的一次性清理覆盖不了运行期故障）。
    loops = start_worker_loops()
    try:
        await asyncio.gather(*loops.values())
    finally:
        for task in loops.values():
            task.cancel()


if __name__ == "__main__":
    import asyncio

    async def _main_with_cleanup():
        try:
            await main()
        finally:
            # Ctrl+C / 异常退出时也要关掉共享 client，避免 Unclosed client 警告
            from services.shared_http import close_shared_client
            from services.stream_manager import close_stream_http_client

            await close_shared_client()
            await close_stream_http_client()

    asyncio.run(_main_with_cleanup())
