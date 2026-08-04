from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel
from app.schemas.critique import CritiqueOutput
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.story import StoryOutput


class GenerateMangaRequest(StrictModel):
    idea: str = Field(min_length=10, max_length=5000)
    target_pages: int = Field(default=4, ge=1, le=12)
    genre: list[str] = Field(default_factory=list, max_length=5)
    audience: str = Field(default="teen")
    manga_style: str = Field(default="modern Japanese black-and-white manga")
    max_revisions: int | None = Field(default=None, ge=0, le=5)
    render_mode: Literal["prompt_only", "mock", "comfyui"] | None = None
    series_id: str | None = Field(default=None, description="Existing series to continue.")
    episode_number: int | None = Field(default=None, ge=1)
    pipeline_mode: Literal["fast", "quality"] = "fast"


class GenerateMangaResponse(StrictModel):
    run_id: str
    status: str
    model: str
    revision_count: int
    story: StoryOutput
    layout: LayoutOutput
    generation: GenerationOutput
    render: RenderOutput
    critique: CritiqueOutput
    series_id: str | None = None
    episode_id: str | None = None
    episode_number: int | None = None


JobState = Literal["queued", "running", "completed", "failed", "cancelled"]
JobStage = Literal[
    "queued",
    "story",
    "layout",
    "generation",
    "render",
    "critique",
    "completed",
    "failed",
    "cancelled",
]


class MangaJobStatus(StrictModel):
    job_id: str
    state: JobState
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: datetime
    updated_at: datetime
    result: GenerateMangaResponse | None = None
    error: str | None = None
