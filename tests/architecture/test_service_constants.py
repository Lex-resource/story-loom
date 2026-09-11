from pathlib import Path

import services.constants as constants


ROOT = Path(__file__).resolve().parents[2]


def test_constants_facade_has_explicit_public_exports():
    source = (ROOT / "services" / "constants.py").read_text(encoding="utf-8")
    assert "import *" not in source
    assert constants.__all__
    assert "EDITOR_DECISION_REWRITE" in constants.__all__
    assert "VECTOR_COLLECTION_PREFIX" in constants.__all__
