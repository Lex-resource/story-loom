from types import SimpleNamespace

from services.novel_memory_views import _latest_atoms


def test_snapshot_views_keep_only_latest_memory_version():
    atoms = [
        SimpleNamespace(memory_key="world_rule:雾城", version=1, statement="旧"),
        SimpleNamespace(memory_key="world_rule:雾城", version=2, statement="新"),
        SimpleNamespace(memory_key="world_rule:档案馆", version=1, statement="另一条"),
    ]

    latest = _latest_atoms(atoms)

    assert {(item.memory_key, item.version) for item in latest} == {
        ("world_rule:雾城", 2),
        ("world_rule:档案馆", 1),
    }
