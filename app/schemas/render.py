from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class PanelRender(StrictModel):
    panel_id: str
    status: Literal["prompt_only", "completed", "failed"]
    backend: Literal["prompt_only", "mock", "comfyui"]
    image_path: str | None = None
    image_url: str | None = None
    prompt_id: str | None = None
    seed: int | None = None
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    error: str | None = None


class PageRender(StrictModel):
    page_number: int = Field(ge=1)
    image_path: str
    image_url: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class PublicationBundle(StrictModel):
    pdf_path: str
    pdf_url: str
    cbz_path: str
    cbz_url: str
    manifest_path: str
    manifest_url: str


class RenderOutput(StrictModel):
    backend: Literal["prompt_only", "mock", "comfyui"]
    checkpoint: str
    workflow_version: str
    panels: list[PanelRender]
    identity_references: dict[str, str] = Field(default_factory=dict)
    pages: list[PageRender] = Field(default_factory=list)
    publication: PublicationBundle | None = None
