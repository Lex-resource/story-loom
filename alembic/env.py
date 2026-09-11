import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from database import Base
from config import require_postgresql_url, settings
# 这些名字看起来「未使用」，实际是让 SQLAlchemy 在 autogenerate/check 之前把表登记进
# Base.metadata —— 少一个模块，`command.check` 就会把那张表报成「需要新建」。
# 工作流相关的两张表（pipeline_configs / workflow_nodes）显式列出而不是靠 models.operations
# 的副作用导入：靠副作用时，谁都可以在不知情的情况下把它们从 metadata 里弄丢。
from models.novel import (  # noqa: F401
    Novel, Chapter, ChapterOutline, Job, RawIssue,
    IssueSummary, LivingDocVersion, VectorOutbox, PromptTemplate,
    PipelineConfigModel, WorkflowNodeDict, SystemNodeDict, SystemDocTypeDict,
)
from models.characters import (
    CharacterArc,
    CharacterCard,
    CharacterCardChangeRecord,
    CharacterCardSnapshot,
    CharacterChapterState,
    CharacterManifest,
    CharacterRelationship,
)
from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.novel_memory import NovelMemoryEvidence, NovelMemoryConflict, NovelMemoryAtom, NovelSceneBlock, ProjectDoctrine
from models.narrative_index import NarrativeIndexEntry

config = context.config


def _database_url() -> str:
    """Resolve the database URL from runtime settings.

    Tests and one-shot tools may provide an explicit config override so they
    can run against a disposable database without changing application config.
    """
    url = (
        config.get_main_option("sqlalchemy.url")
        if config.attributes.get("database_url_override")
        else settings.DATABASE_URL
    )
    return require_postgresql_url(url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not config.attributes.get("database_url_override"):
        url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
