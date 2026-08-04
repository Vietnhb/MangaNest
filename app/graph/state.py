from typing import NotRequired, TypedDict

from app.schemas.critique import CritiqueOutput
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.story import StoryOutput


class MangaState(TypedDict):
    """Shared state passed through every MangaForge LangGraph node."""

    idea: str
    target_pages: int
    genre: list[str]
    audience: str
    manga_style: str
    max_revisions: int
    revision_count: int
    render_mode: str
    episode_number: int | None
    pipeline_mode: str
    continuity_context: NotRequired[dict]
    story: NotRequired[StoryOutput]
    layout: NotRequired[LayoutOutput]
    generation: NotRequired[GenerationOutput]
    render: NotRequired[RenderOutput]
    critique: NotRequired[CritiqueOutput]
