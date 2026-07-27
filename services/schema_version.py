from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_COMMAND = "python scripts/migrate_db.py"


class SchemaVersionError(RuntimeError):
    """Raised when the database schema is not at the application Alembic head."""


@dataclass(frozen=True)
class SchemaContract:
    heads: frozenset[str]
    known_revisions: frozenset[str]


def load_schema_contract() -> SchemaContract:
    config = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    return SchemaContract(
        heads=frozenset(script.get_heads()),
        known_revisions=frozenset(
            revision.revision for revision in script.walk_revisions()
        ),
    )


def validate_schema_revisions(
    current_revisions: Iterable[str],
    contract: SchemaContract,
) -> None:
    current = frozenset(current_revisions)
    if current == contract.heads:
        return
    if not current:
        reason = "database is not initialized with Alembic"
    elif current - contract.known_revisions:
        unknown = ", ".join(sorted(current - contract.known_revisions))
        reason = f"database contains unknown revision(s): {unknown}"
    else:
        actual = ", ".join(sorted(current))
        expected = ", ".join(sorted(contract.heads))
        reason = f"database schema is out of date ({actual}); expected {expected}"
    raise SchemaVersionError(f"{reason}. Run `{MIGRATION_COMMAND}` before startup.")


async def current_schema_revisions(engine: AsyncEngine) -> frozenset[str]:
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            return frozenset(str(row[0]) for row in result.all())
    except SQLAlchemyError as exc:
        raise SchemaVersionError(
            "could not read the Alembic schema version. "
            f"Run `{MIGRATION_COMMAND}` before startup."
        ) from exc


async def assert_schema_current(engine: AsyncEngine) -> None:
    validate_schema_revisions(
        await current_schema_revisions(engine),
        load_schema_contract(),
    )

