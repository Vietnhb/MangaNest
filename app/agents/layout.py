from langchain_core.language_models import BaseChatModel

from app.agents.base import StructuredAgent
from app.prompts.layout import LAYOUT_SYSTEM_PROMPT
from app.schemas.layout import LayoutOutput


class LayoutAgent(StructuredAgent[LayoutOutput]):
    def __init__(self, model: BaseChatModel) -> None:
        super().__init__(model, LayoutOutput, LAYOUT_SYSTEM_PROMPT)
