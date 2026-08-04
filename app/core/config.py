from functools import lru_cache

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MANGAFORGE_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MangaForge AI"
    app_version: str = "0.1.0"
    debug: bool = False
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    llm_provider: Literal["openrouter", "ollama"] = "openrouter"
    vision_provider: Literal["openrouter", "ollama"] = "ollama"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_vision_model: str = "openrouter/free"
    openrouter_free_only: bool = True
    openrouter_site_url: str = "https://mangaforge.ai"
    openrouter_app_name: str = "MangaForge AI"
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=300, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    quality_approval_threshold: float = Field(default=7.5, ge=0, le=10)
    quality_panel_threshold: float = Field(default=7.0, ge=0, le=10)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
    ollama_vision_model: str = "qwen3-vl:4b"
    ollama_temperature: float = Field(default=0.2, ge=0, le=2)
    ollama_num_ctx: int = Field(default=8192, ge=4096)
    ollama_timeout_seconds: float = Field(default=300, gt=0)
    max_generation_revisions: int = Field(default=2, ge=0, le=5)
    agent_semantic_retries: int = Field(default=1, ge=0, le=5)
    database_url: str = "sqlite+aiosqlite:///./data/mangaforge.db"
    render_backend: Literal["prompt_only", "mock", "comfyui"] = "prompt_only"
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_models_dir: str = "E:/MangaForgeAI/models/comfyui"
    comfyui_checkpoint: str = "animagine-xl-4.0-opt.safetensors"
    comfyui_timeout_seconds: float = Field(default=1200, gt=0)
    comfyui_steps: int = Field(default=25, ge=10, le=50)
    comfyui_cfg_scale: float = Field(default=5.0, ge=1, le=15)
    comfyui_sampler: str = "euler_ancestral"
    comfyui_scheduler: str = "normal"
    comfyui_candidates: int = Field(default=2, ge=1, le=4)
    comfyui_candidate_selection: bool = True
    comfyui_ipadapter_enabled: bool = True
    comfyui_ipadapter_weight: float = Field(default=0.42, ge=0, le=1.5)
    comfyui_ipadapter_end_at: float = Field(default=0.65, ge=0.1, le=1)
    render_output_dir: str = "E:/MangaForgeAI/outputs"
    render_max_width: int = Field(default=1216, ge=256, le=4096)
    render_max_height: int = Field(default=1216, ge=256, le=4096)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def active_model(self) -> str:
        return self.openrouter_model if self.llm_provider == "openrouter" else self.ollama_model

    @property
    def active_vision_model(self) -> str:
        return self.openrouter_vision_model if self.vision_provider == "openrouter" else self.ollama_vision_model

    @model_validator(mode="after")
    def enforce_free_openrouter_models(self) -> "Settings":
        if not self.openrouter_free_only:
            return self
        models = []
        if self.llm_provider == "openrouter":
            models.append(self.openrouter_model)
        if self.vision_provider == "openrouter":
            models.append(self.openrouter_vision_model)
        for model in models:
            if model != "openrouter/free" and not model.endswith(":free"):
                raise ValueError("OpenRouter free-only mode accepts openrouter/free or model IDs ending in :free")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
