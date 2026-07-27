import asyncio
import uuid
from types import SimpleNamespace

from services.pipeline_types import VectorOutboxStatus
from worker_support import vector_outbox_worker


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def begin(self):
        return _Transaction()

    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))


class _Factory:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_claim_vector_outboxes_marks_rows_syncing(monkeypatch):
    rows = [SimpleNamespace(id=uuid.uuid4(), status=VectorOutboxStatus.PENDING, updated_at=None)]
    session = _Session(rows)
    monkeypatch.setattr(vector_outbox_worker, "async_session", lambda: _Factory(session))

    claimed = asyncio.run(vector_outbox_worker.claim_vector_outboxes(10))

    assert claimed == [rows[0].id]
    assert rows[0].status == VectorOutboxStatus.SYNCING
    assert session.statement._for_update_arg.skip_locked is True
