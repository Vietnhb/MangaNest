from langchain_core.language_models import BaseChatModel

from app.agents.base import StructuredAgent
from app.prompts.critique import CRITIQUE_SYSTEM_PROMPT
from app.schemas.critique import CritiqueOutput


class CritiqueAgent(StructuredAgent[CritiqueOutput]):
    def __init__(self, model: BaseChatModel) -> None:
        super().__init__(model, CritiqueOutput, CRITIQUE_SYSTEM_PROMPT)
