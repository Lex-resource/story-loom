from __future__ import annotations

from pathlib import Path

import models


ROOT = Path(__file__).resolve().parents[2]


def test_models_package_uses_explicit_exports():
    source = (ROOT / "models" / "__init__.py").read_text(encoding="utf-8")
    assert "import *" not in source
    compatibility_source = (ROOT / "models" / "novel.py").read_text(encoding="utf-8")
    assert "[name for name in globals()" not in compatibility_source
    expected = {
        "Novel",
        "Chapter",
        "Job",
        "CharacterCard",
        "CharacterBranch",
        "NovelMemoryAtom",
        "ProjectDoctrine",
        "RuntimeTunable",
        "NarrativeIndexEntry",
    }
    assert expected <= set(models.__all__)
