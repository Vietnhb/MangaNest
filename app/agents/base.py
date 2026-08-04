from collections.abc import Mapping
from typing import Any, Generic, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredAgent(Generic[OutputT]):
    """Small reusable wrapper around Ollama native structured output."""

    def __init__(
        self,
        model: BaseChatModel,
        output_schema: type[OutputT],
        system_prompt: str,
    ) -> None:
        self.output_schema = output_schema
        self.system_prompt = system_prompt
        self.structured_model = model.with_structured_output(
            output_schema,
            method="json_schema",
        )

    async def ainvoke(self, user_payload: str) -> OutputT:
        result = await self.structured_model.ainvoke(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_payload),
            ]
        )
        if isinstance(result, self.output_schema):
            return result
        if isinstance(result, Mapping):
            return self.output_schema.model_validate(result)
        return cast(OutputT, result)
