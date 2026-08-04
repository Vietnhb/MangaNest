from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import StrictModel
from app.schemas.layout import NormalizedBox


class SeriesCreate(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    premise: str = Field(default="", max_length=5000)
    visual_style: str = Field(default="", max_length=2000)
    world_rules: list[str] = Field(default_factory=list)
    dialogue_rules: list[str] = Field(default_factory=list)


class SeriesPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    premise: str | None = Field(default=None, max_length=5000)
    visual_style: str | None = Field(default=None, max_length=2000)
    world_rules: list[str] | None = None
    dialogue_rules: list[str] | None = None
    expected_version: int = Field(ge=1)


class SeriesSummary(StrictModel):
    id: str
    title: str
    premise: str
    visual_style: str
    version: int
    episode_count: int = 0
    updated_at: datetime


class SpeechBubble(StrictModel):
    bubble_id: str
    line_id: str | None = None
    speaker: str | None = None
    text: str = Field(max_length=2000)
    delivery: str = "normal"
    bubble_type: Literal["speech", "thought", "whisper", "shout", "caption", "sfx"] = "speech"
    box: NormalizedBox
    tail_x: float | None = Field(default=None, ge=0, le=1)
    tail_y: float | None = Field(default=None, ge=0, le=1)
    reading_order: int = Field(ge=1)
    locked: bool = False


class EditablePanel(StrictModel):
    panel_id: str
    box: NormalizedBox
    reading_order: int = Field(ge=1)
    bubbles: list[SpeechBubble] = Field(default_factory=list)
    artwork_locked: bool = False
    panel_locked: bool = False
    status: Literal["draft", "review", "approved", "locked"] = "draft"

    @model_validator(mode="after")
    def validate_geometry(self):
        if self.box.x + self.box.width > 1.000001 or self.box.y + self.box.height > 1.000001:
            raise ValueError("panel box must stay inside its page")
        for bubble in self.bubbles:
            if bubble.box.x + bubble.box.width > 1.000001 or bubble.box.y + bubble.box.height > 1.000001:
                raise ValueError(f"bubble {bubble.bubble_id} must stay inside its panel")
        orders = [bubble.reading_order for bubble in self.bubbles]
        if len(orders) != len(set(orders)):
            raise ValueError("bubble reading_order must be unique inside a panel")
        return self


class EditablePage(StrictModel):
    page_number: int = Field(ge=1)
    panels: list[EditablePanel] = Field(min_length=1)


class EpisodeEditorUpdate(StrictModel):
    expected_revision: int = Field(ge=1)
    pages: list[EditablePage] = Field(min_length=1)
    status: Literal["draft", "review", "approved", "locked"] | None = None

    @model_validator(mode="after")
    def validate_unique_ids(self):
        panel_ids = [panel.panel_id for page in self.pages for panel in page.panels]
        bubble_ids = [bubble.bubble_id for page in self.pages for panel in page.panels for bubble in panel.bubbles]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("panel_id must be unique across the episode")
        if len(bubble_ids) != len(set(bubble_ids)):
            raise ValueError("bubble_id must be unique across the episode")
        return self


class EpisodeDetail(StrictModel):
    id: str
    series_id: str
    run_id: str | None
    episode_number: int
    title: str
    status: str
    revision: int
    story: dict
    layout: dict
    generation: dict
    render: dict
    editor: dict
    continuity_snapshot: dict
    critique: dict | None = None
    created_at: datetime
    updated_at: datetime


class SeriesDetail(SeriesSummary):
    story_bible: dict
    continuity_snapshot: dict
    episodes: list[EpisodeDetail] = Field(default_factory=list)


class RunProjectRef(StrictModel):
    run_id: str
    series_id: str
    episode_id: str
    episode_number: int


class EpisodeRerenderRequest(StrictModel):
    expected_revision: int = Field(ge=1)
    mode: Literal["comfyui"] = "comfyui"
    panel_ids: list[str] | None = Field(default=None, min_length=1, max_length=12)


class PanelPromptUpdate(StrictModel):
    expected_revision: int = Field(ge=1)
    positive_prompt: str = Field(min_length=20, max_length=12000)
    negative_prompt: str = Field(min_length=1, max_length=8000)
    composition_control: str = Field(min_length=3, max_length=4000)
    identity_mode: Literal["auto", "reference", "off"] | None = None
    identity_strength: float | None = Field(default=None, ge=0, le=1.5)


class EpisodeApproveRequest(StrictModel):
    expected_revision: int = Field(ge=1)
