from langchain_core.language_models import BaseChatModel

from app.agents.base import StructuredAgent
from app.prompts.generation import GENERATION_SYSTEM_PROMPT
from app.schemas.generation import GenerationOutput


class GenerationAgent(StructuredAgent[GenerationOutput]):
    def __init__(self, model: BaseChatModel) -> None:
        super().__init__(model, GenerationOutput, GENERATION_SYSTEM_PROMPT)
