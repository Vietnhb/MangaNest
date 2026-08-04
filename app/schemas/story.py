from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class CharacterProfile(StrictModel):
    character_id: str | None = Field(
        default=None,
        description="Stable series-wide ID. Reuse it in every later episode.",
    )
    name: str = Field(description="Character name used consistently in every panel.")
    role: str = Field(description="Narrative role in the story.")
    appearance: str = Field(description="Stable visual identity: face, hair, body, and clothing.")
    personality: str
    motivation: str
    speech_style: str = Field(default="", description="Stable voice, vocabulary, and address rules.")
    current_state: str = Field(default="", description="Physical, emotional, and knowledge state at episode end.")


class DialogueLine(StrictModel):
    line_id: str | None = None
    speaker: str
    text: str
    delivery: str = Field(description="Tone, volume, or emotional delivery.")


class StoryPanel(StrictModel):
    panel_id: str = Field(description="Stable ID in the form p{page}_panel_{number}.")
    panel_number: int = Field(ge=1)
    setting: str
    time_of_day: str
    characters: list[str]
    action: str = Field(description="One drawable action or visual beat.")
    visual_description: str
    shot_type: Literal[
        "extreme_close_up",
        "close_up",
        "medium",
        "full",
        "wide",
        "establishing",
        "over_the_shoulder",
        "point_of_view",
    ]
    camera_angle: Literal["eye_level", "high", "low", "dutch", "top_down", "worm_eye"]
    mood: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    narration: str | None = None
    sound_effects: list[str] = Field(default_factory=list)
    transition: str = Field(description="Relationship to the next panel.")


class StoryPage(StrictModel):
    page_number: int = Field(ge=1)
    purpose: str
    panels: list[StoryPanel] = Field(min_length=1, max_length=9)
    page_turn_hook: str | None = None


class OutlineBeat(StrictModel):
    beat_number: int = Field(ge=1)
    name: str
    summary: str
    emotional_goal: str


class StoryOutput(StrictModel):
    title: str
    logline: str
    genre: list[str]
    themes: list[str]
    visual_tone: str
    characters: list[CharacterProfile] = Field(min_length=1)
    outline: list[OutlineBeat] = Field(min_length=3)
    pages: list[StoryPage] = Field(min_length=1)
    canon_facts: list[str] = Field(default_factory=list)
    continuity_updates: list[str] = Field(default_factory=list)
    unresolved_threads: list[str] = Field(default_factory=list)
