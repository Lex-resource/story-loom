import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import time as _time

import pytest as _pytest


@_pytest.fixture
def freeze_tunables(monkeypatch):
    """冻结 runtime_tunables 快照:单元测试不再触碰真实 DB。

    返回一个 setter,可覆盖个别参数值(freeze_tunables(key=value))。
    覆盖绕过 PARAM_SPECS 校验,专供超时类测试塞 0.01s 这类越界小值。
    """
    from services import runtime_tunables_service as _rts

    monkeypatch.setattr(_rts, "_last_refresh_monotonic", _time.monotonic() + 1e9)

    def _set(**overrides):
        for key, value in overrides.items():
            monkeypatch.setitem(_rts._snapshot, key, value)

    return _set
