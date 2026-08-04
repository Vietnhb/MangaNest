# MangaForge AI

MangaForge AI is a provider-independent manga production platform. It turns a
series bible into scripts, editable page layouts, consistent panel artwork,
deterministic lettering, quality review, and publishable assets.

The production target and migration sequence are documented in
[`docs/architecture.md`](docs/architecture.md). LangGraph runs the typed manga
workflow; model vendors remain replaceable adapters.

The configured workstation runtime, external-SSD layout, and service commands
are documented in [`docs/runtime-setup.md`](docs/runtime-setup.md).

## Workflow

```text
Story Agent -> Layout Agent -> Generation Agent -> ComfyUI -> Vision Critique
                                      ^                            |
                                      |-------- regenerate --------|
```

Critique can send the plan back to Generation without rewriting the approved
story or layout. `MANGAFORGE_MAX_GENERATION_REVISIONS` prevents infinite loops.

## 1. Install Python dependencies

Python 3.12 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Configure the AI provider

The alpha defaults to OpenRouter's free-model router:

```dotenv
MANGAFORGE_LLM_PROVIDER=openrouter
MANGAFORGE_OPENROUTER_API_KEY=replace-me
MANGAFORGE_OPENROUTER_MODEL=openrouter/free
MANGAFORGE_OPENROUTER_VISION_MODEL=openrouter/free
MANGAFORGE_OPENROUTER_FREE_ONLY=true
```

Free-only validation rejects paid model IDs. Ollama remains available as an
optional offline development adapter by setting `MANGAFORGE_LLM_PROVIDER=ollama`.

## 3. Configure the backend

```powershell
Copy-Item .env.example .env
```

Put credentials only in `.env` or a deployment secret manager; never commit them.

## 4. Run the API

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for Swagger UI. Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 5. Run MangaForge Studio

The React + TypeScript dashboard provides the generation form, live service
status, pipeline progress, page layouts, rendered panel gallery, prompt
inspector, critique results, LoRA candidates, and raw JSON output.

The studio uses the cancellable `/manga-jobs` API. Progress is reported from
completed LangGraph nodes rather than estimated in the browser. Demo data is
only loaded when the user explicitly opens the sample project.

The creation screen can continue an existing series. In that mode the backend
loads its Story Bible, character identities, unresolved threads, continuity
snapshot, and the complete previous episode before writing the next episode.
The Storyboard workspace lets artists resize/reposition panels, edit and place
speech balloons independently of artwork, and lock approved elements. Changes
are persisted through the versioned `/story-episodes/{id}/editor` API.

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The dashboard connects to the local API at
`http://127.0.0.1:8000` and automatically loads the included demo result.

## 6. Test the complete pipeline

```powershell
$body = @{
    idea = "Một nữ sinh phát hiện cây bút có thể thay đổi ngày mai"
    target_pages = 2
    genre = @("fantasy", "mystery")
    audience = "teen"
    manga_style = "cinematic black-and-white manga"
    max_revisions = 1
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://127.0.0.1:8000/generate-manga `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

The first call can be delayed by free-provider rate limits or model warm-up. The response
contains `run_id`, `story`, `layout`, `generation`, `render`, `critique`, and
`revision_count`. Every completed run is stored in SQLite at
`data/mangaforge.db`. The stored critique includes `lora_training.eligible`,
caption tags, score, and required rendering metadata for later dataset curation.

## 7. Run automated tests

Tests use fake structured agents and do not require a live AI provider:

```powershell
pytest
```
