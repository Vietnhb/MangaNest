from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class NormalizedBox(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class PanelLayout(StrictModel):
    panel_id: str
    reading_order: int = Field(ge=1)
    box: NormalizedBox
    shape: Literal["rectangle", "vertical", "horizontal", "square", "diagonal", "inset"]
    border: Literal["standard", "thick", "thin", "borderless", "broken"]
    bleed: bool
    focal_weight: Literal["minor", "normal", "major", "splash"]
    composition_notes: str
    balloon_placement: list[str] = Field(default_factory=list)


class PageLayout(StrictModel):
    page_number: int = Field(ge=1)
    reading_direction: Literal["right_to_left"] = "right_to_left"
    page_size_ratio: str = "1:1.414"
    layout_strategy: str
    gutter_notes: str
    panels: list[PanelLayout] = Field(min_length=1)


class LayoutOutput(StrictModel):
    design_rationale: str
    pages: list[PageLayout] = Field(min_length=1)
