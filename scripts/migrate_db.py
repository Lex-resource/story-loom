from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    heads = ScriptDirectory.from_config(config).get_heads()
    print(f"Database schema and ORM metadata are current: {', '.join(heads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
