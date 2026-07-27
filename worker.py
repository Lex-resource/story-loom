import os
from services.logging_config import configure_logging
configure_logging()
from config import mark_worker_process
mark_worker_process()
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from worker_support.orchestrator import (  # noqa: E402,F401
    JobAbortedException,
    JobPausedException,
    check_paused,
    poll_jobs,
    poll_vector_outbox,
    process_generate_job,
    process_job,
    process_single_chapter,
)
from worker_support.orphan_cleaner import cleanup_orphaned_jobs


async def main():
    import asyncio
    from database import init_db

    await init_db()
    await cleanup_orphaned_jobs()
    await asyncio.gather(poll_jobs(), poll_vector_outbox())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
