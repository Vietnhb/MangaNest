from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import manga_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Provider-independent manga production platform powered by LangGraph.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(manga_router)
Path(settings.render_output_dir).mkdir(parents=True, exist_ok=True)
app.mount(
    "/outputs",
    StaticFiles(directory=settings.render_output_dir),
    name="outputs",
)


@app.middleware("http")
async def declare_utf8_json(request, call_next):
    """Keep legacy Windows clients from guessing the encoding of JSON responses."""
    response = await call_next(request)
    if response.headers.get("content-type") == "application/json":
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/system-status", tags=["system"])
async def system_status() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        if settings.llm_provider == "openrouter":
            if settings.openrouter_api_key is None:
                llm = {"online": False, "provider": "openrouter", "model": settings.active_model, "error": "API key is not configured"}
            else:
                try:
                    provider_response = await client.get(
                        f"{settings.openrouter_base_url}/models",
                        headers={"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"},
                    )
                    provider_response.raise_for_status()
                    llm = {"online": True, "provider": "openrouter", "model": settings.active_model, "free_only": settings.openrouter_free_only}
                except Exception as exc:
                    llm = {"online": False, "provider": "openrouter", "model": settings.active_model, "error": str(exc)}
        else:
            try:
                ollama_response = await client.get(f"{settings.ollama_base_url}/api/tags")
                ollama_response.raise_for_status()
                models = [item["name"] for item in ollama_response.json().get("models", [])]
                llm = {"online": True, "provider": "ollama", "model": settings.active_model, "models": models}
            except Exception as exc:
                llm = {"online": False, "provider": "ollama", "model": settings.active_model, "error": str(exc)}
        try:
            comfy_response = await client.get(f"{settings.comfyui_base_url}/system_stats")
            comfy_response.raise_for_status()
            comfyui = {"online": True}
        except Exception as exc:
            comfyui = {"online": False, "error": str(exc)}
        if settings.vision_provider == "ollama":
            try:
                vision_response = await client.get(f"{settings.ollama_base_url}/api/tags")
                vision_response.raise_for_status()
                installed = [item["name"] for item in vision_response.json().get("models", [])]
                vision = {
                    "online": settings.ollama_vision_model in installed,
                    "provider": "ollama",
                    "model": settings.ollama_vision_model,
                }
            except Exception as exc:
                vision = {"online": False, "provider": "ollama", "model": settings.ollama_vision_model, "error": str(exc)}
        else:
            vision = {"online": llm["online"], "provider": "openrouter", "model": settings.openrouter_vision_model}
    models_dir = Path(settings.comfyui_models_dir)
    checkpoint_path = models_dir / "checkpoints" / settings.comfyui_checkpoint
    clip_vision_path = models_dir / "clip_vision" / "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
    ipadapter_path = models_dir / "ipadapter" / "ip-adapter-plus-face_sdxl_vit-h.safetensors"
    return {
        "status": "ok" if llm["online"] and vision["online"] and comfyui["online"] else "degraded",
        "llm": llm,
        "vision": vision,
        "comfyui": comfyui,
        "render_backend": settings.render_backend,
        "checkpoint": {
            "name": settings.comfyui_checkpoint,
            "ready": checkpoint_path.exists(),
        },
        "identity_conditioning": {
            "enabled": settings.comfyui_ipadapter_enabled,
            "ready": clip_vision_path.exists() and ipadapter_path.exists(),
            "engine": "IP-Adapter Plus Face SDXL + multi-view character bible",
        },
        "output_directory": settings.render_output_dir,
    }
