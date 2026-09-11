"""Worker adapter for character branch generation."""

from services.character_branch_generation import process_character_branch_job as _process
from worker_support.generation_nodes import editor, planner, validator_agent, writer


async def process_character_branch_job(db, job) -> None:
    await _process(
        db,
        job,
        planner_node=planner,
        writer_node=writer,
        editor_node=editor,
        validator_node=validator_agent,
    )
