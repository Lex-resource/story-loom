import asyncio
from types import SimpleNamespace

from services.pipeline_types import VectorOutboxStatus
from services.storage_authority import STORAGE_AUTHORITIES, storage_consistency_report, storage_health_report


def test_structured_state_has_one_authority_and_vectors_are_rebuildable():
    authoritative = {item.name for item in STORAGE_AUTHORITIES if item.source_of_truth}
    assert authoritative == {"postgresql", "living_docs_outline_files"}
    chroma = next(item for item in STORAGE_AUTHORITIES if item.name == "chromadb")
    assert chroma.source_of_truth is False
    assert "VectorOutbox" in chroma.recovery


def test_storage_health_report_describes_configured_roots():
    report = storage_health_report()
    assert set(report["checks"]) == {"living_docs", "chroma", "settings_parent"}
    assert all("path" in check and "writable" in check for check in report["checks"].values())


def test_storage_consistency_report_marks_failed_outbox_degraded():
    class Db:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(all=lambda: [(VectorOutboxStatus.FAILED, 2)])
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    report = asyncio.run(storage_consistency_report(Db()))
    assert report["status"] == "degraded"
    assert report["vector_outbox"] == {"failed": 2}
