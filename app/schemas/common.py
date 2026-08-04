from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base schema that rejects fields not declared by MangaForge."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
