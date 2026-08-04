# MangaForge Production Architecture

Status: Active target architecture. The workstation runtime is a development adapter, not the product architecture.

## Product position

MangaForge is an end-to-end manga production system, not an image generator with a gallery. Its durable advantage must come from structured story continuity, character identity, editable page composition, deterministic lettering, selective regeneration, collaboration, and publishing.

The product must outperform single-purpose tools by joining these workflows in one versioned project:

1. Series bible and episode continuity.
2. Script, beats, page budget, and right-to-left panel planning.
3. Character sheets, identity references, LoRA lifecycle, and costume versions.
4. Per-panel image generation and local correction.
5. Editable panels, balloons, captions, SFX, and typography.
6. Automated quality checks plus human approval.
7. Team review, version history, export, and eventual creator marketplace.

## Product workflow benchmark

MangaMaker's public product surface was reviewed as a workflow benchmark, not as a source of proprietary implementation details. The verified interaction model is: choose or draw a layout, generate a whole page or an individual panel, reuse selected character references, repair or upscale in place, edit bubbles and typography as overlays, then export. Its dashboard also separates reusable character, location, and sticker sheets. Public updates show scoped prompt tokens such as `#GlobalClothingStyle`, editable overlay spacing/transparency, and background-removed insertable elements.

MangaForge adopts the following domain logic from that benchmark and from comic-production research:

1. `Series library`: versioned character, costume, location, prop, and sticker assets. Assets are selected explicitly per panel instead of being hidden inside a long prompt.
2. `Scoped tokens`: project and asset tokens resolve into a panel render recipe only when selected. Updating a costume creates a new version and does not silently rewrite approved art.
3. `Layout first`: reading order, gutters, safe margins, bleed, focal weight, and dialogue reservations exist before image generation.
4. `Panel recipe`: subject identities, pose/shot control, location reference, prompt, seed, model, and correction history are stored independently for every panel.
5. `Local correction`: reroll, face/hand inpaint, background replacement, upscale, and element insertion create artwork versions without regenerating approved neighboring panels.
6. `Lettering last`: dialogue, captions, SFX, vertical text, tails, fonts, and spacing remain deterministic vector-like layers.
7. `Release gate`: fresh visual review plus human approval is required before 300/600 DPI, PDF, or CBZ export.

### Adopted core business flow

The supplied four-stage base is used as an implementation contract:

1. `Script decomposition`: typed story, scene, camera, action, emotion, dialogue, narration, and SFX data.
2. `Character and prompt compilation`: approved multi-view character anchors plus a bounded, tag-ordered Animagine prompt compiler. Dialogue never enters the diffusion prompt.
3. `Panel rendering`: headless ComfyUI jobs produce artwork-only panel versions. A single 4 GB worker renders sequentially; parallel fan-out belongs at the queue/GPU-pool level, not as concurrent requests competing on one GPU.
4. `Deterministic finishing`: Pillow composes the stored layout, performs pixel-measured Unicode wrapping, renders bubbles/tails/captions/SFX, and builds publication artifacts only after approval.

Instructor, Fal.ai, and Replicate are not dependencies because the existing Pydantic, LangGraph, and provider adapters already own those responsibilities. Celery is not introduced into the alpha merely as a second job abstraction; Redis-backed durable workers remain a Stage 2 replacement for the in-process job store. This preserves the useful business boundaries without duplicating infrastructure.

Reference conditioning is adaptive, not globally forced. A general IP-Adapter reference can transfer reference composition and destroy wide or multi-character scenes. In `auto` mode MangaForge therefore disables a full-image portrait reference for wide shots, reflections, and multiple subjects, and allows a per-panel `reference` or `off` override. FaceID is opt-in because InsightFace does not reliably detect stylized manga portraits and its pretrained face models are not licensed as a commercial production default. Spatial masks, ControlNet pose/depth/line controls, and character-layer compositing must not be simulated by merely adding more prompt text.

### Character-first production gate

Panel generation begins only after each recurring character has an approved visual bible. The minimum reference set is `front`, `three_quarter`, `profile`, `back`, `full_body`, and `expression`. A creator can import art or approve generated candidates. Each asset is versioned independently, records outfit and style scope, and must be replaceable without rewriting story text.

For every panel the render recipe selects the nearest approved camera view instead of reusing one portrait everywhere. Multiple reference embeddings may be averaged on low-VRAM workers, but spatial attention masks are required when a character occupies only part of the panel. Wide and multi-character panels use separate character layers or masked inpainting before compositing. Only the resulting composite proceeds to lettering and visual review.

## Architecture principles

- No model vendor is part of the domain model. Every inference backend is an adapter behind a provider interface.
- AI output is a proposal. Canonical story, character, layout, and lettering data are versioned application state.
- Panels are generated independently and pages are composed deterministically.
- API processes never own durable jobs. Jobs, leases, retries, and cancellation survive restarts.
- Original images and derived assets live in object storage, not local API disks.
- Every run records provider, model, prompt version, seed, workflow version, latency, token usage, cost, and quality result.
- Free inference is an alpha-stage constraint, not a scaling strategy.

## Target topology

```text
Web / Mobile / Desktop clients
            |
       CDN + WAF
            |
 API Gateway / Auth / Rate Limits
            |
       FastAPI control plane
       /        |          \
PostgreSQL   Redis       Object Storage + CDN
       \        |          /
        Durable workflow queue
       /          |           \
Story workers  Image workers  Quality workers
       |          |           |
 Model Gateway  GPU Scheduler  Vision Gateway
       |          |           |
OpenRouter /   ComfyUI API /   OpenRouter /
vLLM / APIs    managed GPUs    vLLM / APIs
            |
 OpenTelemetry + Prometheus + logs + error tracking
```

## Runtime boundaries

### Control plane

FastAPI owns authentication context, projects, permissions, subscriptions, idempotency keys, signed uploads, job creation, approvals, and read APIs. It does not perform long inference inside request handlers.

PostgreSQL is authoritative for users, organizations, series, episodes, story-bible versions, editor revisions, jobs, asset metadata, usage, and audit events. Redis is transient coordination for queues, leases, rate limits, and realtime progress only.

### Workflow plane

LangGraph remains useful for the typed manga workflow and conditional quality loop, but graphs execute inside durable workers. Queue delivery is at-least-once, so each stage must be idempotent and persist checkpoints. A production queue can begin with Redis-backed workers, then move to Temporal when multi-hour workflows and operational volume justify it.

### Model gateway

The application calls a provider-neutral interface for text and vision. Current adapters:

- `openrouter`: primary alpha provider, configured with `openrouter/free` and free-only enforcement.
- `ollama`: local fallback and the current deterministic `qwen3-vl:4b` visual release gate.

Future adapters can target vLLM, managed inference, or direct model vendors without changing agents or stored project data. Provider selection is policy-driven by capability, latency, reliability, privacy, and budget.

OpenRouter free routing is allowed during alpha. Its availability and rate limits are external constraints, so production launch requires measured capacity plus a self-hosted or paid fallback.

### Image plane

ComfyUI is a workflow execution adapter, not the public service boundary. Image workers submit versioned workflows to a GPU pool. The scheduler controls concurrency per GPU, memory class, retry policy, cancellation, and warm model placement.

Animagine XL is the current baseline, not a permanent product dependency. Checkpoints, LoRAs, ControlNet, reference adapters, inpainting, and upscalers are selected from a versioned render recipe. Approved panels are immutable; corrections generate a new asset version.

## Manga data model

```text
Organization
  -> Project / Series
      -> StoryBibleVersion
      -> CharacterVersion -> ReferenceAssets -> LoRAVersion
      -> Episode
          -> ScriptVersion
          -> PageVersion
              -> PanelVersion -> ArtworkVersions
                              -> Balloon / Caption / SFX layers
          -> Review / Approval / Export
```

Text is never baked into generated artwork. Panel geometry, reading order, crop, dialogue, balloon shape, tail target, font, and SFX are independent editable layers. Optimistic revision checks prevent silent overwrites.

## Reliability and safety requirements

- Idempotency keys for job creation and payment-affecting operations.
- Exponential backoff with jitter and provider-aware `Retry-After` handling.
- Dead-letter queue and replay tools.
- Per-tenant quotas, abuse prevention, content policy, and audit logs.
- Signed object-storage URLs, malware scanning, encrypted secrets, and key rotation.
- Database backups with tested restore procedures.
- Canary model/workflow releases and instant rollback.
- SLOs for API availability, queue delay, panel success rate, and export correctness.
- Cost and latency budgets enforced per workflow stage.

## Delivery sequence

### Stage 1 — credible alpha

- Provider-independent LLM/vision adapters.
- OpenRouter free-only routing with Ollama fallback.
- Real manga canvas, persistent editor revisions, selective panel rerender, PDF/CBZ export.
- Reusable character/location/prop sheets, scoped prompt tokens, and per-panel identity controls.
- Provider/model/run telemetry and explicit failure states.

### Stage 2 — multi-user beta

- Authentication, organizations, PostgreSQL, Redis queue, object storage, background GPU workers.
- Resumable jobs, realtime progress, project permissions, comments, version history.
- Character reference pipeline, inpainting, typography system, automated visual regression tests.

### Stage 3 — scalable launch

- Containerized services, autoscaling workers, CDN, WAF, observability, backups, incident runbooks.
- vLLM or managed-provider capacity for predictable text/vision throughput.
- GPU pool scheduling, workflow canaries, usage metering, subscriptions, moderation, support tooling.

### Stage 4 — platform advantage

- Collaborative teams, reusable characters/worlds, creator templates, asset marketplace, localization, print workflows, and public API.
- Quality ranking driven by approved production data, never by unreviewed generations.

## Current repository status

The repository has completed part of Stage 1. It still uses SQLite, an in-process job store, local output storage, and one ComfyUI worker. Those components are explicitly development adapters and must be replaced before public multi-user launch.

## Engineering references

- MangaMaker public workflow and feature surface: https://mangamaker.app/
- ComicCamp human-in-the-loop story/script/illustration/lettering framework: https://creativity-ai.github.io/assets/papers/70.pdf
- IP-Adapter Plus node behavior and reference-conditioning controls: https://github.com/cubiq/ComfyUI_IPAdapter_plus
- InstantID capabilities, single-face limitation, and InsightFace licensing warning: https://github.com/instantX-research/InstantID
- ControlNet pose, depth, edge, and line conditioning: https://github.com/lllyasviel/ControlNet
- Animagine XL 4.0 tag ordering, quality tags, settings, and resolution guidance: https://huggingface.co/cagliostrolab/animagine-xl-4.0
- Supported PyTorch CUDA installation matrix: https://pytorch.org/get-started/previous-versions/
- Layout-controllable manga diffusion: https://arxiv.org/abs/2412.19303
- Retrieval-augmented comic identity and costume consistency: https://arxiv.org/abs/2506.12517

- OpenRouter free router and capability-aware model selection: https://openrouter.ai/openrouter/free
- OpenRouter provider/model fallbacks: https://openrouter.ai/docs/guides/routing/model-fallbacks
- OpenRouter rate-limit and retry behavior: https://openrouter.ai/docs/api/reference/errors-and-debugging
- vLLM serving and production observability: https://docs.vllm.ai/en/latest/cli/serve/
- NVIDIA Triton scheduling, batching, health, and metrics: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/architecture.html
- KServe autoscaling, revisions, and traffic management: https://kserve.github.io/website/docs/concepts/architecture/control-plane
