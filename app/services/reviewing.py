import logging

import httpx

from app.agents import VisionCritiqueAgent
from app.core.config import Settings
from app.schemas.critique import CritiqueOutput, LoRATrainingCandidate, PanelCritique
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.story import StoryOutput
from app.services.llm import create_vision_model
from app.services.quality_checks import detect_embedded_panel_grid

logger = logging.getLogger(__name__)


async def review_episode_render(
    *, settings: Settings, story: StoryOutput, layout: LayoutOutput,
    generation: GenerationOutput, render: RenderOutput, revision_count: int,
) -> CritiqueOutput:
    """Run a fresh visual release gate against the exact currently rendered assets."""
    completed = {
        panel.panel_id: panel for panel in render.panels
        if panel.status == "completed" and panel.image_path
    }
    panel_ids = [panel.panel_id for page in story.pages for panel in page.panels]
    payload = {
        "task": "Review the exact current manga render and make a release decision.",
        "input": {
            "story": story.model_dump(mode="json"),
            "layout": layout.model_dump(mode="json"),
            "generation": generation.model_dump(mode="json"),
            "render": render.model_dump(mode="json"),
            "revision_count": revision_count,
            "release_threshold": settings.quality_approval_threshold,
            "panel_threshold": settings.quality_panel_threshold,
        },
    }
    try:
        if settings.vision_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(
                        f"{settings.comfyui_base_url}/free",
                        json={"unload_models": True, "free_memory": True},
                    )
            except Exception:
                logger.warning("Could not release ComfyUI models before local review", exc_info=True)
        critique = await VisionCritiqueAgent(create_vision_model(settings)).ainvoke(
            payload,
            [completed[panel_id].image_path for panel_id in panel_ids if panel_id in completed],
        )
        if {item.panel_id for item in critique.panel_critiques} != set(panel_ids):
            raise ValueError("Vision review did not return every panel ID")
    except Exception as exc:
        logger.exception("Fresh vision review failed")
        critique = CritiqueOutput(
            overall_score=0,
            decision="regenerate",
            summary="Automated visual review failed; export is blocked until a successful review.",
            panel_critiques=[
                PanelCritique(
                    panel_id=panel_id, score=0, strengths=[],
                    issues=["Fresh visual review unavailable."],
                    correction="Retry quality review before approval.",
                )
                for panel_id in panel_ids
            ],
            regeneration_instructions=["Retry visual quality review."],
            lora_training=LoRATrainingCandidate(
                eligible=False, reason=f"Visual review failed: {type(exc).__name__}",
                caption_tags=[], quality_score=0, required_metadata=["successful_visual_review"],
            ),
        )

    grid_failures = {
        panel_id for panel_id, panel in completed.items()
        if detect_embedded_panel_grid(panel.image_path)
    }
    if grid_failures:
        reviewed = [
            item.model_copy(update={
                "score": min(item.score, 4.5),
                "issues": list(dict.fromkeys([*item.issues, "Embedded multi-panel grid detected."])),
                "correction": "Render exactly one uninterrupted borderless scene.",
            }) if item.panel_id in grid_failures else item
            for item in critique.panel_critiques
        ]
        critique = critique.model_copy(update={
            "overall_score": min(critique.overall_score, 5.0),
            "decision": "regenerate",
            "panel_critiques": reviewed,
        })
    if critique.overall_score < settings.quality_approval_threshold or any(
        item.score < settings.quality_panel_threshold for item in critique.panel_critiques
    ):
        critique = critique.model_copy(update={"decision": "regenerate"})
    return critique
