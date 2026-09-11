import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from main import app
from models.operations import Job
from services import project_service
from routers.pipeline import GenerateRequest
from routers.projects import CreateProjectRequest
from services.pipeline_types import VectorOutboxStatus
from pydantic import ValidationError
import pytest


def test_active_generate_job_has_postgresql_partial_unique_index():
    index = next(item for item in Job.__table__.indexes if item.name == "uq_jobs_active_generate_project")
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert index.unique is True
    assert "generate" in predicate
    assert "pending" in predicate and "running" in predicate


def test_route_map_exposes_generation_controls_and_no_secret_get():
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("/api/writing/{project_id}/pause", "POST") in routes
    assert ("/api/writing/{project_id}/resume", "POST") in routes
    assert ("/api/writing/{project_id}/rewrite", "POST") in routes
    assert ("/api/writing/{project_id}/intervention", "POST") not in routes
    assert ("/api/settings/api-key", "GET") not in routes


def test_project_list_is_read_only():
    now = datetime.now(timezone.utc)
    novel = SimpleNamespace(
        id="project-1",
        title="Novel",
        status="paused",
        novel_format="long_webnovel",
        creative_profile={},
        target_chapters=10,
        word_count_per_chapter=3000,
        created_at=now,
        updated_at=now,
    )

    class Db:
        commits = 0

        async def execute(self, _statement):
            return SimpleNamespace(all=lambda: [(novel, 2, 6000)])

        async def commit(self):
            self.commits += 1

    db = Db()
    result = asyncio.run(project_service.list_projects(db))
    assert result[0]["total_chars"] == 6000
    assert db.commits == 0


def test_vector_outbox_status_values_are_stable():
    assert VectorOutboxStatus.PENDING.value == "pending"
    assert VectorOutboxStatus.SYNCING.value == "syncing"


def test_request_models_reject_blank_projects_and_oversized_batches():
    with pytest.raises(ValidationError):
        CreateProjectRequest(title="   ", user_prompt="prompt")
    with pytest.raises(ValidationError):
        GenerateRequest(batch_size=101)
