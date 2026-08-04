from langchain_core.language_models import BaseChatModel

from app.agents.base import StructuredAgent
from app.prompts.story import STORY_SYSTEM_PROMPT
from app.schemas.story import StoryOutput


class StoryAgent(StructuredAgent[StoryOutput]):
    def __init__(self, model: BaseChatModel) -> None:
        super().__init__(model, StoryOutput, STORY_SYSTEM_PROMPT)
