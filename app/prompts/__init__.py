"""Versioned system prompts for MangaForge agents."""

from app.prompts.critique import CRITIQUE_SYSTEM_PROMPT
from app.prompts.generation import GENERATION_SYSTEM_PROMPT
from app.prompts.layout import LAYOUT_SYSTEM_PROMPT
from app.prompts.story import STORY_SYSTEM_PROMPT

__all__ = [
    "CRITIQUE_SYSTEM_PROMPT",
    "GENERATION_SYSTEM_PROMPT",
    "LAYOUT_SYSTEM_PROMPT",
    "STORY_SYSTEM_PROMPT",
]
