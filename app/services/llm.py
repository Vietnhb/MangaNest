from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import Settings


def _openrouter_model(settings: Settings, *, vision: bool) -> ChatOpenAI:
    if settings.openrouter_api_key is None:
        raise RuntimeError("MANGAFORGE_OPENROUTER_API_KEY is required when LLM provider is openrouter")
    return ChatOpenAI(
        model=settings.openrouter_vision_model if vision else settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0 if vision else settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        default_headers={"HTTP-Referer": settings.openrouter_site_url, "X-Title": settings.openrouter_app_name},
    )


def create_chat_model(settings: Settings) -> BaseChatModel:
    """Build the configured provider without coupling the workflow to its SDK."""
    if settings.llm_provider == "openrouter":
        return _openrouter_model(settings, vision=False)

    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        num_ctx=settings.ollama_num_ctx,
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
        async_client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )


def create_vision_model(settings: Settings) -> BaseChatModel:
    if settings.vision_provider == "openrouter":
        return _openrouter_model(settings, vision=True)
    return ChatOllama(
        model=settings.ollama_vision_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=min(settings.ollama_num_ctx, 16384),
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
        async_client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )
