from pathlib import Path

from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_v48_is_recognized_as_the_next_experiment_version(tmp_path):
    context = ExperimentContext(
        run_id="v48-memory-merge",
        prompt_version="V48",
        variant="ariadne-a34-memory-merge",
        project_id="project",
        chapter_index=3,
        root_dir=Path(tmp_path),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V47")
        assert prompt_version_at_least("V48")
    finally:
        deactivate(token)
