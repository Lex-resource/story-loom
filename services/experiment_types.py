from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentConfig(BaseModel):
    """Opt-in local research metadata carried by a generation Job."""

    run_id: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(default="V0", pattern=r"^V[0-9]+$")
    variant: str = Field(default="baseline", min_length=1, max_length=120)
    root_dir: str | None = Field(default=None, max_length=500)
