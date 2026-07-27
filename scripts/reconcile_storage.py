from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import async_session
from services.storage_authority import storage_consistency_report
from services.storage_repair import reset_replayable_vector_outbox
from worker_support.vector_outbox_worker import claim_vector_outboxes, process_vector_outbox


async def replay_pending() -> int:
    processed = 0
    while True:
        outbox_ids = await claim_vector_outboxes(100)
        if not outbox_ids:
            return processed
        for outbox_id in outbox_ids:
            await process_vector_outbox(outbox_id)
            processed += 1


async def run(repair: bool) -> int:
    reset_count = 0
    if repair:
        async with async_session() as db:
            reset_count = await reset_replayable_vector_outbox(db)
        processed_count = await replay_pending()
    else:
        processed_count = 0

    async with async_session() as db:
        report = await storage_consistency_report(db)
    print(json.dumps({
        "reset_vector_outbox_rows": reset_count,
        "processed_vector_outbox_rows": processed_count,
        "report": report,
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Report or explicitly repair storage projections.")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Reset failed/expired vector outbox rows and replay all pending rows.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.repair))


if __name__ == "__main__":
    raise SystemExit(main())
