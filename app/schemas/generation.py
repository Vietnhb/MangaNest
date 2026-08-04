from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class GenerationParameters(StrictModel):
    aspect_ratio: str
    width: int = Field(ge=256, le=4096)
    height: int = Field(ge=256, le=4096)
    steps: int = Field(ge=1, le=150)
    cfg_scale: float = Field(ge=1, le=30)
    sampler: str


class PanelGenerationPrompt(StrictModel):
    panel_id: str
    positive_prompt: str = Field(description="English prompt ready for a manga diffusion model.")
    negative_prompt: str = Field(description="English exclusions for common visual failures.")
    character_consistency: list[str]
    composition_control: str
    identity_mode: Literal["auto", "reference", "off"] = "auto"
    identity_strength: float | None = Field(default=None, ge=0, le=1.5)
    dialogue_overlay: list[str] = Field(
        default_factory=list,
        description="Text to add in post-processing, never ask the image model to render it.",
    )
    parameters: GenerationParameters


class GenerationOutput(StrictModel):
    prompt_language: Literal["English"] = "English"
    recommended_checkpoint: str
    global_style_prefix: str
    global_negative_prefix: str
    panels: list[PanelGenerationPrompt] = Field(min_length=1)
    continuity_notes: list[str]
    revision_summary: str | None = None
