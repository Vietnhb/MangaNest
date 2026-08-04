from collections import deque
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.graph.workflow import AgentBundle
from app.schemas.critique import CritiqueOutput, LoRATrainingCandidate, PanelCritique
from app.schemas.generation import (
    GenerationOutput,
    GenerationParameters,
    PanelGenerationPrompt,
)
from app.schemas.layout import LayoutOutput, NormalizedBox, PageLayout, PanelLayout
from app.schemas.render import PanelRender, RenderOutput
from app.schemas.story import (
    CharacterProfile,
    OutlineBeat,
    StoryOutput,
    StoryPage,
    StoryPanel,
)

OutputT = TypeVar("OutputT", bound=BaseModel)


class FakeAgent(Generic[OutputT]):
    def __init__(self, *outputs: OutputT) -> None:
        self.outputs = deque(outputs)
        self.calls = 0

    async def ainvoke(self, user_payload: str) -> OutputT:
        self.calls += 1
        if len(self.outputs) > 1:
            return self.outputs.popleft()
        return self.outputs[0]


def story_output() -> StoryOutput:
    return StoryOutput(
        title="The Last Ink",
        logline="A student discovers that her drawings can alter tomorrow.",
        genre=["fantasy"],
        themes=["responsibility"],
        visual_tone="High-contrast black-and-white manga",
        characters=[
            CharacterProfile(
                name="Aki",
                role="protagonist",
                appearance="Short black bob, round glasses, dark school uniform",
                personality="Curious and cautious",
                motivation="Protect her friend",
            )
        ],
        outline=[
            OutlineBeat(beat_number=1, name="Discovery", summary="Aki finds a pen.", emotional_goal="Wonder"),
            OutlineBeat(beat_number=2, name="Test", summary="The ink moves.", emotional_goal="Tension"),
            OutlineBeat(beat_number=3, name="Choice", summary="Aki accepts responsibility.", emotional_goal="Resolve"),
        ],
        pages=[
            StoryPage(
                page_number=1,
                purpose="Introduce the supernatural pen.",
                panels=[
                    StoryPanel(
                        panel_id="p1_panel_1",
                        panel_number=1,
                        setting="Quiet art classroom",
                        time_of_day="sunset",
                        characters=["Aki"],
                        action="Aki lifts a pen that leaks glowing black ink.",
                        visual_description="Dusty classroom and a thin ribbon of moving ink.",
                        shot_type="close_up",
                        camera_angle="eye_level",
                        mood="uneasy wonder",
                        dialogue=[],
                        narration=None,
                        sound_effects=["drip"],
                        transition="moment_to_moment",
                    )
                ],
                page_turn_hook="The ink points toward the window.",
            )
        ],
    )


def layout_output() -> LayoutOutput:
    return LayoutOutput(
        design_rationale="One large reveal panel gives the discovery room to breathe.",
        pages=[
            PageLayout(
                page_number=1,
                layout_strategy="Single cinematic reveal",
                gutter_notes="Standard outer safe area",
                panels=[
                    PanelLayout(
                        panel_id="p1_panel_1",
                        reading_order=1,
                        box=NormalizedBox(x=0.05, y=0.05, width=0.9, height=0.9),
                        shape="rectangle",
                        border="standard",
                        bleed=False,
                        focal_weight="major",
                        composition_notes="Place Aki on the right and ink trail on the left.",
                        balloon_placement=[],
                    )
                ],
            )
        ],
    )


def generation_output(revision: str | None = None) -> GenerationOutput:
    return GenerationOutput(
        recommended_checkpoint="generic manga diffusion checkpoint",
        global_style_prefix="monochrome manga, crisp ink, screentone",
        global_negative_prefix="color, text, watermark, malformed anatomy",
        panels=[
            PanelGenerationPrompt(
                panel_id="p1_panel_1",
                positive_prompt="monochrome manga close-up, Aki, short black bob, round glasses, dark school uniform, lifting a pen with glowing black ink, sunset classroom",
                negative_prompt="color, text, letters, watermark, extra fingers, inconsistent clothing",
                character_consistency=["Aki: short black bob, round glasses, dark school uniform"],
                composition_control="Aki right third, moving ink leading toward left edge",
                dialogue_overlay=["SFX: drip"],
                parameters=GenerationParameters(
                    aspect_ratio="2:3",
                    width=768,
                    height=1152,
                    steps=30,
                    cfg_scale=6.5,
                    sampler="DPM++ 2M Karras",
                ),
            )
        ],
        continuity_notes=["Keep Aki's glasses and uniform identical."],
        revision_summary=revision,
    )


def critique_output(decision: str = "accept") -> CritiqueOutput:
    return CritiqueOutput(
        overall_score=8.5 if decision == "accept" else 5.0,
        decision=decision,
        summary="The prompt plan is ready." if decision == "accept" else "Improve composition specificity.",
        panel_critiques=[
            PanelCritique(
                panel_id="p1_panel_1",
                score=8.5 if decision == "accept" else 5.0,
                strengths=["Character traits are explicit."],
                issues=[] if decision == "accept" else ["Composition is underspecified."],
                correction=None if decision == "accept" else "State the subject position and ink direction.",
            )
        ],
        regeneration_instructions=[] if decision == "accept" else ["Clarify p1_panel_1 composition."],
        lora_training=LoRATrainingCandidate(
            eligible=decision == "accept",
            reason="Complete metadata" if decision == "accept" else "Needs prompt revision",
            caption_tags=["manga", "classroom", "close-up"],
            quality_score=8.5 if decision == "accept" else 5.0,
            required_metadata=["checkpoint", "seed", "render review"],
        ),
    )


def render_output() -> RenderOutput:
    return RenderOutput(
        backend="prompt_only",
        checkpoint="mock-model",
        workflow_version="test-v1",
        panels=[
            PanelRender(
                panel_id="p1_panel_1",
                status="prompt_only",
                backend="prompt_only",
                width=768,
                height=1152,
            )
        ],
    )


def agent_bundle(*critiques: CritiqueOutput) -> AgentBundle:
    return AgentBundle(
        story=FakeAgent(story_output()),
        layout=FakeAgent(layout_output()),
        generation=FakeAgent(generation_output(), generation_output("Critique applied")),
        critique=FakeAgent(*critiques),
    )
