from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field

from app.schemas.common import StrictModel


def _normalize_ten_point_score(value: Any) -> Any:
    """Accept a common local-model mistake: returning 0-100 scores."""
    if isinstance(value, (int, float)) and 10 < value <= 100:
        return value / 10
    return value


TenPointScore = Annotated[float, BeforeValidator(_normalize_ten_point_score), Field(ge=0, le=10)]


class PanelCritique(StrictModel):
    panel_id: str
    score: TenPointScore
    strengths: list[str]
    issues: list[str]
    correction: str | None = None


class LoRATrainingCandidate(StrictModel):
    eligible: bool
    reason: str
    caption_tags: list[str]
    quality_score: TenPointScore
    required_metadata: list[str]


class CritiqueOutput(StrictModel):
    overall_score: TenPointScore
    decision: Literal["accept", "regenerate", "accept_with_warnings"]
    summary: str
    panel_critiques: list[PanelCritique] = Field(min_length=1)
    regeneration_instructions: list[str] = Field(default_factory=list)
    lora_training: LoRATrainingCandidate
