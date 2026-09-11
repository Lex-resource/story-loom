import asyncio
import uuid
from types import SimpleNamespace

from services.character_branch_vector_service import branch_vector_collection_name
from services.pipeline_types import VectorOutboxStatus
from worker_support import vector_outbox_worker


def test_archived_branch_outbox_is_discarded_without_upsert(monkeypatch):
    branch_id = uuid.uuid4()
    outbox = SimpleNamespace(
        id=uuid.uuid4(),
        status=VectorOutboxStatus.SYNCING,
        project_id=uuid.uuid4(),
        chapter_index=1,
        payload={
            "collection_name": branch_vector_collection_name(branch_id),
            "items": [{"id": "branch-item", "description": "must not return"}],
        },
    )
    deleted = []
    commits = []

    class _Db:
        async def get(self, model, _key):
            if model is vector_outbox_worker.VectorOutbox:
                return outbox
            raise AssertionError("unexpected get")

        async def execute(self, _statement):
            return SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(
                    id=branch_id, status="archived"
                )
            )

        async def delete(self, value):
            deleted.append(value)

        async def commit(self):
            commits.append(True)

    class _Factory:
        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_args):
            return False

    async def fail_upsert(**_kwargs):
        raise AssertionError("archived branch must not be projected")

    monkeypatch.setattr(vector_outbox_worker, "async_session", lambda: _Factory())
    monkeypatch.setattr(vector_outbox_worker, "upsert_to_collection", fail_upsert)

    asyncio.run(vector_outbox_worker.process_vector_outbox(outbox.id))

    assert deleted == [outbox]
    assert commits == [True]
