# Development Workstation Runtime

This document describes one developer workstation. It is not the production deployment guide.

## Services

- FastAPI: `http://127.0.0.1:8000`
- React studio: `http://127.0.0.1:5173`
- ComfyUI image worker: `http://127.0.0.1:8188`
- OpenRouter free router: primary text and vision provider
- Ollama: optional offline fallback

Large image assets remain under `E:\MangaForgeAI` during development. Production assets must move to S3-compatible object storage and a CDN.

## Start local services

```powershell
powershell -ExecutionPolicy Bypass -File deploy\comfyui\start-comfyui.ps1
powershell -ExecutionPolicy Bypass -File deploy\start-mangaforge.ps1
```

The active `.env` uses `MANGAFORGE_LLM_PROVIDER=openrouter`, `MANGAFORGE_OPENROUTER_MODEL=openrouter/free`, and `MANGAFORGE_OPENROUTER_FREE_ONLY=true`. Never commit API keys. Use a secret manager in hosted environments.

To work offline, switch `MANGAFORGE_LLM_PROVIDER=ollama` and configure the local text and vision models. This fallback does not define the production architecture.

## Image development baseline

Animagine XL 4.0 Opt currently runs through ComfyUI with sequential panel generation, stable identity seeds, selective rerender, and deterministic lettering overlays. This low-VRAM mode validates workflows; production uses independently scalable image workers and versioned object-storage assets.
