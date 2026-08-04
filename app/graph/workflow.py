import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol, TypeVar

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agents import (
    CritiqueAgent,
    GenerationAgent,
    LayoutAgent,
    StoryAgent,
    VisionCritiqueAgent,
)
from app.core.config import Settings, get_settings
from app.graph.state import MangaState
from app.schemas.critique import CritiqueOutput, LoRATrainingCandidate, PanelCritique
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.story import StoryOutput
from app.services.llm import create_chat_model, create_vision_model
from app.services.layout_engine import build_professional_layout
from app.services.rendering import RenderMode, RenderingService, create_renderer
from app.services.quality_checks import detect_embedded_panel_grid

OutputT = TypeVar("OutputT", bound=BaseModel)
logger = logging.getLogger(__name__)


class AgentLike(Protocol[OutputT]):
    async def ainvoke(self, user_payload: str) -> OutputT: ...


class VisionAgentLike(Protocol):
    async def ainvoke(
        self, payload: dict[str, Any], image_paths: list[str]
    ) -> CritiqueOutput: ...


@dataclass(frozen=True)
class AgentBundle:
    story: AgentLike[StoryOutput]
    layout: AgentLike[LayoutOutput]
    generation: AgentLike[GenerationOutput]
    critique: AgentLike[CritiqueOutput]
    vision_critique: VisionAgentLike | None = None


def create_agent_bundle(settings: Settings) -> AgentBundle:
    model = create_chat_model(settings)
    vision_model = create_vision_model(settings)
    return AgentBundle(
        story=StoryAgent(model),
        layout=LayoutAgent(model),
        generation=GenerationAgent(model),
        critique=CritiqueAgent(model),
        vision_critique=VisionCritiqueAgent(vision_model),
    )


def _json_payload(task: str, data: dict[str, Any]) -> str:
    return json.dumps(
        {"task": task, "input": data},
        ensure_ascii=False,
        indent=2,
    )


def _story_panel_ids(story: StoryOutput) -> list[str]:
    return [panel.panel_id for page in story.pages for panel in page.panels]


def _layout_panel_ids(layout: LayoutOutput) -> list[str]:
    return [panel.panel_id for page in layout.pages for panel in page.panels]


def _generation_panel_ids(generation: GenerationOutput) -> list[str]:
    return [panel.panel_id for panel in generation.panels]


def _lock_generation_to_story(story: StoryOutput, generation: GenerationOutput) -> GenerationOutput:
    """Enforce canonical character anchors and exact lettering for every panel."""
    characters = {character.name.casefold(): character for character in story.characters}
    story_panels = {panel.panel_id: panel for page in story.pages for panel in page.panels}
    locked_panels = []
    for prompt in generation.panels:
        story_panel = story_panels[prompt.panel_id]
        canonical_anchors = []
        for name in story_panel.characters:
            character = characters.get(name.casefold())
            if character is not None:
                canonical_anchors.append(
                    f"{character.character_id or character.name}: {character.name}; {character.appearance}"
                )
        anchors = list(dict.fromkeys([*canonical_anchors, *prompt.character_consistency]))
        prompt_lower = prompt.positive_prompt.casefold()
        missing_anchors = [
            anchor for anchor in canonical_anchors
            if anchor.split("; ", 1)[-1].casefold() not in prompt_lower
        ]
        prompt_text = ", ".join([*missing_anchors, prompt.positive_prompt])
        lettering = [line.text for line in story_panel.dialogue]
        if story_panel.narration:
            lettering.append(story_panel.narration)
        lettering.extend(story_panel.sound_effects)
        locked_panels.append(prompt.model_copy(update={
            "positive_prompt": prompt_text,
            "character_consistency": anchors,
            "dialogue_overlay": lettering,
        }))
    return generation.model_copy(update={"panels": locked_panels})


def _apply_character_canon(story: StoryOutput, context: dict[str, Any] | None) -> StoryOutput:
    """Stamp stable IDs and restore identity fields from the authoritative bible."""
    bible_characters = (context or {}).get("story_bible", {}).get("characters", [])
    by_id = {item.get("character_id"): item for item in bible_characters if item.get("character_id")}
    by_name = {item.get("name", "").casefold(): item for item in bible_characters if item.get("name")}
    canonical = []
    for character in story.characters:
        source = by_id.get(character.character_id) or by_name.get(character.name.casefold())
        stable_id = (source or {}).get("character_id") or character.character_id
        if not stable_id:
            digest = hashlib.sha1(character.name.casefold().encode("utf-8")).hexdigest()[:12]
            stable_id = f"char_{digest}"
        updates = {"character_id": stable_id}
        if source:
            for field in ("name", "role", "appearance", "personality", "speech_style"):
                if source.get(field) not in (None, ""):
                    updates[field] = source[field]
        canonical.append(character.model_copy(update=updates))
    return story.model_copy(update={"characters": canonical})


def _safe_fallback_critique(state: MangaState, reason: Exception) -> CritiqueOutput:
    """Never discard completed renders because a local critic emitted bad JSON."""
    completed = {panel.panel_id for panel in state["render"].panels if panel.status == "completed"}
    panel_ids = _story_panel_ids(state["story"])
    all_rendered = bool(panel_ids) and completed == set(panel_ids)
    score = 7.0 if all_rendered else 5.0
    issue = "AI critique unavailable; human review required before approval."
    logger.error("Critique fallback activated: %s", reason)
    return CritiqueOutput(
        overall_score=score,
        decision="accept_with_warnings",
        summary=(
            "All panels were rendered and preserved, but the local Critique Agent returned "
            "invalid structured data. The product is available for human review."
            if all_rendered else
            "The Critique Agent returned invalid structured data and some panels may be incomplete."
        ),
        panel_critiques=[
            PanelCritique(
                panel_id=panel_id,
                score=score if panel_id in completed else 3.0,
                strengths=["Render completed and preserved"] if panel_id in completed else [],
                issues=[issue],
                correction="Review this panel in MangaForge Studio.",
            )
            for panel_id in panel_ids
        ],
        regeneration_instructions=[],
        lora_training=LoRATrainingCandidate(
            eligible=False,
            reason="Human review is required because automated critique could not be parsed.",
            caption_tags=[],
            quality_score=score,
            required_metadata=["human_review", "render_metadata"],
        ),
    )


def _validate_layout_geometry(layout: LayoutOutput) -> None:
    """Reject boxes that overflow or materially overlap on the manga page."""

    epsilon = 0.005
    for page in layout.pages:
        for panel in page.panels:
            box = panel.box
            if box.x + box.width > 1 + epsilon or box.y + box.height > 1 + epsilon:
                raise ValueError(f"{panel.panel_id} extends outside the page")
        for index, first in enumerate(page.panels):
            if first.shape == "inset":
                continue
            for second in page.panels[index + 1 :]:
                if second.shape == "inset":
                    continue
                horizontal = min(
                    first.box.x + first.box.width,
                    second.box.x + second.box.width,
                ) - max(first.box.x, second.box.x)
                vertical = min(
                    first.box.y + first.box.height,
                    second.box.y + second.box.height,
                ) - max(first.box.y, second.box.y)
                if horizontal > epsilon and vertical > epsilon:
                    raise ValueError(
                        f"{first.panel_id} overlaps {second.panel_id}"
                    )


def _ensure_exact_panel_coverage(expected: list[str], actual: list[str], stage: str) -> None:
    if len(actual) != len(set(actual)):
        raise ValueError(f"{stage} returned duplicate panel IDs")
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        raise ValueError(
            f"{stage} panel coverage mismatch; missing={missing}, unexpected={unexpected}"
        )


def build_manga_graph(
    agents: AgentBundle | None = None,
    settings: Settings | None = None,
    renderer: RenderingService | None = None,
):
    """Build and compile the complete four-agent workflow."""

    runtime_settings = settings or get_settings()
    agent_bundle = agents or create_agent_bundle(runtime_settings)
    rendering_service = renderer or create_renderer(runtime_settings)

    async def story_node(state: MangaState) -> dict[str, Any]:
        input_data = {
            "idea": state["idea"],
            "target_pages": state["target_pages"],
            "preferred_genres": state["genre"],
            "audience": state["audience"],
            "manga_style": state["manga_style"],
        }
        if state.get("continuity_context"):
            input_data["mandatory_series_continuity"] = state["continuity_context"]
        correction: str | None = None
        for _ in range(runtime_settings.agent_semantic_retries + 1):
            if correction:
                input_data["mandatory_correction"] = correction
            story = await agent_bundle.story.ainvoke(
                _json_payload(
                    "Develop the idea into a manga outline and detailed panels.",
                    input_data,
                )
            )
            story = _apply_character_canon(story, state.get("continuity_context"))
            panel_ids = _story_panel_ids(story)
            if (
                len(story.pages) == state["target_pages"]
                and len(panel_ids) == len(set(panel_ids))
            ):
                return {"story": story}
            correction = (
                f"Previous output was invalid: output exactly {state['target_pages']} page(s), "
                "with globally unique panel IDs. Rebuild the JSON and obey this exactly."
            )
        raise ValueError(correction or "Story Agent semantic validation failed")

    async def layout_node(state: MangaState) -> dict[str, Any]:
        story = state["story"]
        try:
            async with asyncio.timeout(min(runtime_settings.ollama_timeout_seconds, 60)):
                layout = await agent_bundle.layout.ainvoke(
                    _json_payload(
                        "Propose a professional page composition. Geometry must be valid.",
                        {"story": story.model_dump(mode="json")},
                    )
                )
            if len(layout.pages) != len(story.pages):
                raise ValueError("page count changed")
            _validate_layout_geometry(layout)
        except Exception as exc:
            logger.warning(
                "Layout Agent proposal unavailable (%s); using safe manga templates",
                type(exc).__name__,
            )
            layout = build_professional_layout(story)
        _ensure_exact_panel_coverage(
            _story_panel_ids(story),
            _layout_panel_ids(layout),
            "Layout Agent",
        )
        _validate_layout_geometry(layout)
        return {"layout": layout}

    async def generation_node(state: MangaState) -> dict[str, Any]:
        prior_critique = state.get("critique")
        is_revision = prior_critique is not None and prior_critique.decision == "regenerate"
        revision_count = state["revision_count"] + (1 if is_revision else 0)
        input_data: dict[str, Any] = {
            "story": state["story"].model_dump(mode="json"),
            "layout": state["layout"].model_dump(mode="json"),
            "manga_style": state["manga_style"],
            "revision_number": revision_count,
        }
        if state.get("continuity_context"):
            input_data["series_visual_memory"] = {
                "story_bible": state["continuity_context"].get("story_bible", {}),
                "continuity_snapshot": state["continuity_context"].get("continuity_snapshot", {}),
            }
        if is_revision:
            input_data["critique_feedback"] = prior_critique.model_dump(mode="json")

        correction: str | None = None
        for _ in range(runtime_settings.agent_semantic_retries + 1):
            if correction:
                input_data["mandatory_correction"] = correction
            generation = await agent_bundle.generation.ainvoke(
                _json_payload("Create one diffusion prompt for every panel.", input_data)
            )
            try:
                _ensure_exact_panel_coverage(
                    _story_panel_ids(state["story"]),
                    _generation_panel_ids(generation),
                    "Generation Agent",
                )
                generation = _lock_generation_to_story(state["story"], generation)
                return {"generation": generation, "revision_count": revision_count}
            except ValueError as exc:
                correction = (
                    f"Previous output was invalid ({exc}). Return exactly one prompt for each "
                    f"panel ID: {_story_panel_ids(state['story'])}"
                )
        raise ValueError(correction or "Generation Agent semantic validation failed")

    async def critique_node(state: MangaState) -> dict[str, Any]:
        critique_payload = {
            "task": "Review the complete manga generation and make a release decision.",
            "input": {
                "story": state["story"].model_dump(mode="json"),
                "layout": state["layout"].model_dump(mode="json"),
                "generation": state["generation"].model_dump(mode="json"),
                "render": state["render"].model_dump(mode="json"),
                "revision_count": state["revision_count"],
                "remaining_revisions": max(
                    state["max_revisions"] - state["revision_count"], 0
                ),
            },
        }
        image_paths = [
            panel.image_path
            for panel in state["render"].panels
            if panel.status == "completed" and panel.image_path
        ]
        use_vision = (
            state["render"].backend == "comfyui"
            and bool(image_paths)
            and agent_bundle.vision_critique is not None
        )
        expected_ids = set(_story_panel_ids(state["story"]))
        try:
            if use_vision:
                critique = await agent_bundle.vision_critique.ainvoke(
                    critique_payload, image_paths
                )
            else:
                critique = await agent_bundle.critique.ainvoke(
                    json.dumps(critique_payload, ensure_ascii=False, indent=2)
                )
            reviewed_ids = {item.panel_id for item in critique.panel_critiques}
            if reviewed_ids != expected_ids:
                raise ValueError("Critique Agent did not review every storyboard panel")
        except Exception as first_error:
            logger.warning("Primary critique failed (%s); attempting text-only recovery", type(first_error).__name__)
            try:
                recovery_payload = {
                    **critique_payload,
                    "mandatory_correction": (
                        "Return strictly valid JSON matching CritiqueOutput. Use scores from 0 to 10 "
                        f"and review exactly these panel IDs: {sorted(expected_ids)}."
                    ),
                }
                critique = await agent_bundle.critique.ainvoke(
                    json.dumps(recovery_payload, ensure_ascii=False, indent=2)
                )
                reviewed_ids = {item.panel_id for item in critique.panel_critiques}
                if reviewed_ids != expected_ids:
                    raise ValueError("Recovery critique did not review every storyboard panel")
            except Exception as recovery_error:
                critique = _safe_fallback_critique(state, recovery_error)

        rendered_by_id = {
            panel.panel_id: panel for panel in state["render"].panels
            if panel.status == "completed" and panel.image_path
        }
        grid_failures = (
            {
                panel_id for panel_id, panel in rendered_by_id.items()
                if detect_embedded_panel_grid(panel.image_path)
            }
            if state["render"].backend == "comfyui"
            else set()
        )
        if grid_failures:
            reviewed = []
            for item in critique.panel_critiques:
                if item.panel_id in grid_failures:
                    reviewed.append(item.model_copy(update={
                        "score": min(item.score, 4.5),
                        "issues": list(dict.fromkeys([
                            *item.issues,
                            "Artwork contains an embedded multi-panel grid instead of one scene.",
                        ])),
                        "correction": (
                            "Regenerate as one uninterrupted full-bleed scene with no internal "
                            "frames, gutters, borders, collage, or split-screen composition."
                        ),
                    }))
                else:
                    reviewed.append(item)
            critique = critique.model_copy(update={
                "overall_score": min(critique.overall_score, 5.0),
                "decision": "regenerate",
                "summary": (
                    f"{critique.summary} Automatic preflight rejected embedded panel grids in: "
                    f"{', '.join(sorted(grid_failures))}."
                ),
                "panel_critiques": reviewed,
                "regeneration_instructions": list(dict.fromkeys([
                    *critique.regeneration_instructions,
                    "Render each flagged panel as exactly one borderless scene.",
                ])),
            })

        if (
            critique.decision == "regenerate"
            and state["revision_count"] >= state["max_revisions"]
        ):
            critique = critique.model_copy(
                update={
                    "decision": "accept_with_warnings",
                    "summary": (
                        f"{critique.summary} Maximum generation revisions reached; "
                        "returning the latest plan with warnings."
                    ),
                }
            )
        return {"critique": critique}

    async def render_node(state: MangaState) -> dict[str, Any]:
        prior_critique = state.get("critique")
        previous_render = state.get("render")
        generation_to_render = state["generation"]
        reusable_panels = {}
        if (
            state["render_mode"] == "comfyui"
            and prior_critique is not None
            and prior_critique.decision == "regenerate"
            and previous_render is not None
            and previous_render.backend == "comfyui"
        ):
            flagged_ids = {
                item.panel_id
                for item in prior_critique.panel_critiques
                if item.score < 8 or item.issues or item.correction
            }
            if flagged_ids:
                generation_to_render = state["generation"].model_copy(update={
                    "panels": [
                        panel for panel in state["generation"].panels
                        if panel.panel_id in flagged_ids
                    ]
                })
                reusable_panels = {
                    panel.panel_id: panel
                    for panel in previous_render.panels
                    if panel.panel_id not in flagged_ids and panel.status == "completed"
                }

        render = await rendering_service.render(
            generation_to_render,
            state["revision_count"],
            state["render_mode"],  # type: ignore[arg-type]
        )
        if reusable_panels:
            newly_rendered = {panel.panel_id: panel for panel in render.panels}
            render = render.model_copy(update={
                "panels": [
                    newly_rendered.get(panel.panel_id) or reusable_panels[panel.panel_id]
                    for panel in state["generation"].panels
                ]
            })
        _ensure_exact_panel_coverage(
            _story_panel_ids(state["story"]),
            [panel.panel_id for panel in render.panels],
            "Rendering service",
        )
        return {"render": render}

    def route_after_critique(state: MangaState) -> Literal["generation", "end"]:
        return "generation" if state["critique"].decision == "regenerate" else "end"

    builder = StateGraph(MangaState)
    builder.add_node("story", story_node)
    builder.add_node("layout", layout_node)
    builder.add_node("generation", generation_node)
    builder.add_node("render", render_node)
    builder.add_node("critique", critique_node)
    builder.add_edge(START, "story")
    builder.add_edge("story", "layout")
    builder.add_edge("layout", "generation")
    builder.add_edge("generation", "render")
    builder.add_edge("render", "critique")
    builder.add_conditional_edges(
        "critique",
        route_after_critique,
        {"generation": "generation", "end": END},
    )
    return builder.compile()


@lru_cache
def get_manga_graph():
    return build_manga_graph()
