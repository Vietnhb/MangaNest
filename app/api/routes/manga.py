import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import Settings, get_settings
from app.db.repository import RunRepository, get_run_repository
from app.graph.workflow import get_manga_graph
from app.schemas.api import GenerateMangaRequest, GenerateMangaResponse
from app.schemas.api import MangaJobStatus
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.story import StoryOutput
from app.schemas.memory import EpisodeApproveRequest, EpisodeDetail, EpisodeEditorUpdate, EpisodeRerenderRequest, PanelPromptUpdate, RunProjectRef, SeriesCreate, SeriesDetail, SeriesPatch, SeriesSummary
from app.services.jobs import build_initial_state, manga_job_store
from app.services.rendering import create_renderer
from app.services.publishing import publish_episode
from app.services.reviewing import review_episode_render
from app.services.demo import DEMO_PANELS, demo_panel_svg, demo_project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["manga"])


@router.get("/demo-project")
async def get_demo_project() -> dict:
    """Return a complete offline sample that demonstrates the production workflow."""
    return demo_project()


@router.get("/demo-art/{panel_id}.svg", response_class=Response)
async def get_demo_panel_art(panel_id: str) -> Response:
    if panel_id not in {panel["panel_id"] for panel in DEMO_PANELS}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo panel not found")
    return Response(content=demo_panel_svg(panel_id), media_type="image/svg+xml")


@router.post(
    "/generate-manga",
    response_model=GenerateMangaResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_manga(
    request: GenerateMangaRequest,
    graph: Annotated[Any, Depends(get_manga_graph)],
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> GenerateMangaResponse:
    """Run Story, Layout, Generation, and Critique as one pipeline."""

    try:
        continuity = await repository.load_generation_context(request.series_id) if hasattr(repository, "load_generation_context") else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if continuity and request.episode_number in continuity.get("existing_episode_numbers", []):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Episode {request.episode_number} already exists")
    initial_state = build_initial_state(request, settings, continuity)

    try:
        result = await graph.ainvoke(initial_state, {"recursion_limit": 20})
    except Exception as exc:
        logger.exception("Manga generation pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Manga pipeline failed. Verify the configured LLM provider, credentials, "
                "rate limits, and structured-output support. "
                f"Cause: {exc}"
            ),
        ) from exc

    run_id = await repository.save(
        request=request,
        model_name=settings.active_model,
        revision_count=result["revision_count"],
        story=result["story"],
        layout=result["layout"],
        generation=result["generation"],
        render=result["render"],
        critique=result["critique"],
    )
    project_ref = await repository.get_run_project_ref(run_id) if hasattr(repository, "get_run_project_ref") else None
    published_render = result["render"]
    if project_ref and hasattr(repository, "get_episode"):
        episode = await repository.get_episode(project_ref.episode_id)
        if episode is not None:
            published_render = RenderOutput.model_validate(episode.render)

    return GenerateMangaResponse(
        run_id=run_id,
        status=result["critique"].decision,
        model=settings.active_model,
        revision_count=result["revision_count"],
        story=result["story"],
        layout=result["layout"],
        generation=result["generation"],
        render=published_render,
        critique=result["critique"],
        series_id=project_ref.series_id if project_ref else None,
        episode_id=project_ref.episode_id if project_ref else None,
        episode_number=project_ref.episode_number if project_ref else None,
    )


@router.post(
    "/manga-jobs",
    response_model=MangaJobStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_manga_job(
    request: GenerateMangaRequest,
    graph: Annotated[Any, Depends(get_manga_graph)],
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> MangaJobStatus:
    """Start a cancellable manga job and return immediately."""

    try:
        continuity = await repository.load_generation_context(request.series_id) if hasattr(repository, "load_generation_context") else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if continuity and request.episode_number in continuity.get("existing_episode_numbers", []):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Episode {request.episode_number} already exists")
    return manga_job_store.create(request, graph, settings, repository, continuity)


@router.get("/manga-jobs/{job_id}", response_model=MangaJobStatus)
async def get_manga_job(job_id: str) -> MangaJobStatus:
    job = manga_job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/manga-jobs", response_model=list[MangaJobStatus])
async def list_manga_jobs() -> list[MangaJobStatus]:
    return manga_job_store.list()


@router.post("/manga-jobs/{job_id}/cancel", response_model=MangaJobStatus)
async def cancel_manga_job(job_id: str) -> MangaJobStatus:
    job = manga_job_store.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/story-series", response_model=SeriesDetail, status_code=status.HTTP_201_CREATED)
async def create_story_series(payload: SeriesCreate, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> SeriesDetail:
    return await repository.create_series(payload)


@router.get("/story-series", response_model=list[SeriesSummary])
async def list_story_series(repository: Annotated[RunRepository, Depends(get_run_repository)]) -> list[SeriesSummary]:
    return await repository.list_series()


@router.get("/story-series/{series_id}", response_model=SeriesDetail)
async def get_story_series(series_id: str, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> SeriesDetail:
    result = await repository.get_series(series_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return result


@router.get("/story-series/{series_id}/latest-result", response_model=GenerateMangaResponse)
async def get_latest_series_result(
    series_id: str,
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> GenerateMangaResponse:
    result = await repository.get_latest_series_result(series_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series has no completed production")
    return result


@router.patch("/story-series/{series_id}", response_model=SeriesDetail)
async def patch_story_series(series_id: str, payload: SeriesPatch, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> SeriesDetail:
    try:
        result = await repository.patch_series(series_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Series was changed elsewhere; reload before saving") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return result


@router.get("/story-episodes/{episode_id}", response_model=EpisodeDetail)
async def get_story_episode(episode_id: str, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> EpisodeDetail:
    result = await repository.get_episode(episode_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.put("/story-episodes/{episode_id}/editor", response_model=EpisodeDetail)
async def update_story_episode_editor(episode_id: str, payload: EpisodeEditorUpdate, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> EpisodeDetail:
    try:
        result = await repository.update_episode_editor(episode_id, payload)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Episode is locked") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode was changed elsewhere; reload before saving") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.post("/story-episodes/{episode_id}/rerender", response_model=EpisodeDetail)
async def rerender_story_episode(
    episode_id: str,
    payload: EpisodeRerenderRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> EpisodeDetail:
    episode = await repository.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if episode.revision != payload.expected_revision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode was changed elsewhere; reload before rendering")
    try:
        generation = GenerationOutput.model_validate(episode.generation)
        requested_ids = set(payload.panel_ids or [panel.panel_id for panel in generation.panels])
        known_ids = {panel.panel_id for panel in generation.panels}
        if not requested_ids <= known_ids:
            unknown = sorted(requested_ids - known_ids)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown panel IDs: {unknown}")
        locked_ids = {
            panel.get("panel_id")
            for page in episode.editor.get("pages", [])
            for panel in page.get("panels", [])
            if panel.get("artwork_locked") or panel.get("panel_locked")
        }
        if requested_ids & locked_ids:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Locked panels cannot be rendered: {sorted(requested_ids & locked_ids)}",
            )
        generation_subset = generation.model_copy(update={
            "panels": [panel for panel in generation.panels if panel.panel_id in requested_ids]
        })
        current_render = RenderOutput.model_validate(episode.render)
        reusable_references = (
            current_render.identity_references
            if current_render.workflow_version in {"sdxl-ipadapter-identity-v4", "sdxl-ipadapter-identity-v5"}
            else {}
        )
        rendered = await create_renderer(settings).render(
            generation_subset,
            episode.revision,
            payload.mode,
            identity_references=reusable_references,
        )
        if payload.panel_ids:
            updated = {panel.panel_id: panel for panel in rendered.panels}
            rendered = rendered.model_copy(update={
                "panels": [updated.get(panel.panel_id, panel) for panel in current_render.panels],
                "identity_references": {**current_render.identity_references, **rendered.identity_references},
                "pages": [],
                "publication": None,
            })
        rendered = await asyncio.to_thread(
            publish_episode,
            episode_id=episode.id,
            title=episode.title,
            episode_number=episode.episode_number,
            render=rendered,
            editor_payload=episode.editor,
            output_dir=settings.render_output_dir,
            allow_export=False,
        )
        critique = await review_episode_render(
            settings=settings,
            story=StoryOutput.model_validate(episode.story),
            layout=LayoutOutput.model_validate(episode.layout),
            generation=generation,
            render=rendered,
            revision_count=episode.revision,
        )
        result = await repository.update_episode_render(
            episode_id, payload.expected_revision, rendered, critique
        )
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Episode is locked") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode changed while rendering; reload and try again") from exc
    except Exception as exc:
        logger.exception("Episode rerender failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"ComfyUI render failed: {exc}") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.put("/story-episodes/{episode_id}/generation/panels/{panel_id}", response_model=EpisodeDetail)
async def update_panel_prompt(
    episode_id: str,
    panel_id: str,
    payload: PanelPromptUpdate,
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> EpisodeDetail:
    try:
        result = await repository.update_episode_panel_prompt(episode_id, panel_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Episode is locked") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode changed elsewhere; reload before editing") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panel not found") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.post("/story-episodes/{episode_id}/approve", response_model=EpisodeDetail)
async def approve_story_episode(
    episode_id: str,
    payload: EpisodeApproveRequest,
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> EpisodeDetail:
    try:
        result = await repository.approve_episode(episode_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Episode is locked") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode changed elsewhere; reload before approval") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fresh quality review does not meet the release threshold.",
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.post("/story-episodes/{episode_id}/review", response_model=EpisodeDetail)
async def review_story_episode(
    episode_id: str,
    payload: EpisodeApproveRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[RunRepository, Depends(get_run_repository)],
) -> EpisodeDetail:
    """Re-run the visual release gate without paying for another image render."""
    episode = await repository.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if episode.revision != payload.expected_revision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode changed elsewhere; reload before review")
    render = RenderOutput.model_validate(episode.render)
    critique = await review_episode_render(
        settings=settings,
        story=StoryOutput.model_validate(episode.story),
        layout=LayoutOutput.model_validate(episode.layout),
        generation=GenerationOutput.model_validate(episode.generation),
        render=render,
        revision_count=episode.revision,
    )
    try:
        result = await repository.update_episode_render(
            episode_id, payload.expected_revision, render, critique
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Episode changed during review; reload and retry") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return result


@router.get("/manga-runs/{run_id}/project", response_model=RunProjectRef)
async def get_run_project(run_id: str, repository: Annotated[RunRepository, Depends(get_run_repository)]) -> RunProjectRef:
    result = await repository.get_run_project_ref(run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project memory not found")
    return result
