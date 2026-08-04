import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.db.repository import RunRepository
from app.schemas.api import GenerateMangaRequest, GenerateMangaResponse, MangaJobStatus
from app.schemas.render import RenderOutput

logger = logging.getLogger(__name__)

NEXT_STAGE = {
    "story": ("layout", 25, "Kịch bản hoàn tất · đang dàn trang manga"),
    "layout": ("generation", 45, "Bố cục hoàn tất · đang tối ưu prompt"),
    "generation": ("render", 65, "Prompt hoàn tất · đang dựng hình panel"),
    "render": ("critique", 82, "Hình ảnh hoàn tất · đang kiểm tra chất lượng"),
}


def build_initial_state(request: GenerateMangaRequest, settings: Settings, continuity_context: dict | None = None) -> dict[str, Any]:
    state = {
        "idea": request.idea,
        "target_pages": request.target_pages,
        "genre": request.genre,
        "audience": request.audience,
        "manga_style": request.manga_style,
        "max_revisions": (
            request.max_revisions
            if request.max_revisions is not None
            else settings.max_generation_revisions
        ),
        "revision_count": 0,
        "render_mode": request.render_mode or settings.render_backend,
        "episode_number": request.episode_number,
        "pipeline_mode": request.pipeline_mode,
    }
    if continuity_context:
        state["continuity_context"] = continuity_context
    return state


class MangaJobStore:
    """In-memory local job runner with truthful LangGraph node progress."""

    def __init__(self) -> None:
        self.jobs: dict[str, MangaJobStatus] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.worker_lock = asyncio.Lock()

    def create(
        self,
        request: GenerateMangaRequest,
        graph: Any,
        settings: Settings,
        repository: RunRepository,
        continuity_context: dict | None = None,
    ) -> MangaJobStatus:
        now = datetime.now(UTC)
        job_id = uuid4().hex
        job = MangaJobStatus(
            job_id=job_id,
            state="queued",
            stage="queued",
            progress=0,
            message="Đã xếp hàng, chuẩn bị model",
            created_at=now,
            updated_at=now,
        )
        self.jobs[job_id] = job
        self.tasks[job_id] = asyncio.create_task(
            self._run(job_id, request, graph, settings, repository, continuity_context)
        )
        return job

    def get(self, job_id: str) -> MangaJobStatus | None:
        return self.jobs.get(job_id)

    def list(self) -> list[MangaJobStatus]:
        return sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)

    def cancel(self, job_id: str) -> MangaJobStatus | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        task = self.tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        if job.state in {"queued", "running"}:
            self._update(
                job_id,
                state="cancelled",
                stage="cancelled",
                message="Đã hủy tác vụ",
            )
        return self.jobs[job_id]

    def _update(self, job_id: str, **changes: Any) -> None:
        current = self.jobs[job_id]
        self.jobs[job_id] = current.model_copy(
            update={**changes, "updated_at": datetime.now(UTC)}
        )

    async def _run(
        self,
        job_id: str,
        request: GenerateMangaRequest,
        graph: Any,
        settings: Settings,
        repository: RunRepository,
        continuity_context: dict | None = None,
    ) -> None:
        if self.worker_lock.locked():
            self._update(
                job_id,
                state="queued",
                stage="queued",
                progress=1,
                message="Đang chờ lượt GPU; dự án của bạn đã được giữ an toàn",
            )
        async with self.worker_lock:
            await self._execute(
                job_id, request, graph, settings, repository, continuity_context
            )

    async def _execute(
        self,
        job_id: str,
        request: GenerateMangaRequest,
        graph: Any,
        settings: Settings,
        repository: RunRepository,
        continuity_context: dict | None = None,
    ) -> None:
        state = build_initial_state(request, settings, continuity_context)
        self._update(
            job_id,
            state="running",
            stage="story",
            progress=5,
            message="Đang viết kịch bản và chia panel",
        )
        try:
            async for update in graph.astream(
                state,
                {"recursion_limit": 20},
                stream_mode="updates",
            ):
                for node, values in update.items():
                    if isinstance(values, dict):
                        state.update(values)
                    if node in NEXT_STAGE:
                        next_stage, progress, message = NEXT_STAGE[node]
                        revision = state.get("revision_count", 0)
                        if revision and node in {"generation", "render"}:
                            message = f"{message} · bản sửa {revision}"
                        self._update(
                            job_id,
                            stage=next_stage,
                            progress=progress,
                            message=message,
                        )
                    elif node == "critique":
                        critique = state.get("critique")
                        if critique and critique.decision == "regenerate":
                            self._update(
                                job_id,
                                stage="generation",
                                progress=50,
                                message="Kiểm duyệt yêu cầu sửa · đang tạo bản mới",
                            )
                        else:
                            self._update(
                                job_id,
                                stage="critique",
                                progress=96,
                                message="Kiểm duyệt hoàn tất · đang đóng gói dự án",
                            )

            run_id = await repository.save(
                request=request,
                model_name=settings.active_model,
                revision_count=state["revision_count"],
                story=state["story"],
                layout=state["layout"],
                generation=state["generation"],
                render=state["render"],
                critique=state["critique"],
            )
            project_ref = await repository.get_run_project_ref(run_id) if hasattr(repository, "get_run_project_ref") else None
            published_render = state["render"]
            if project_ref and hasattr(repository, "get_episode"):
                episode = await repository.get_episode(project_ref.episode_id)
                if episode is not None:
                    published_render = RenderOutput.model_validate(episode.render)
            result = GenerateMangaResponse(
                run_id=run_id,
                status=state["critique"].decision,
                model=settings.active_model,
                revision_count=state["revision_count"],
                story=state["story"],
                layout=state["layout"],
                generation=state["generation"],
                render=published_render,
                critique=state["critique"],
                series_id=project_ref.series_id if project_ref else None,
                episode_id=project_ref.episode_id if project_ref else None,
                episode_number=project_ref.episode_number if project_ref else None,
            )
            self._update(
                job_id,
                state="completed",
                stage="completed",
                progress=100,
                message="Manga đã sẵn sàng để duyệt",
                result=result,
            )
        except asyncio.CancelledError:
            self._update(
                job_id,
                state="cancelled",
                stage="cancelled",
                message="Đã hủy tác vụ",
            )
        except Exception as exc:
            logger.exception("Manga background job failed")
            failed_stage = self.jobs[job_id].stage
            exception_name = type(exc).__name__
            detail = str(exc).strip()
            if exception_name in {"ReadTimeout", "TimeoutError"}:
                error = (
                    f"{failed_stage.title()} Agent vượt quá thời gian chờ. "
                    "Hãy thử 1 trang hoặc dùng chế độ bản nháp."
                )
            else:
                error = f"{failed_stage.title()} Agent: {detail or exception_name}"
            self._update(
                job_id,
                state="failed",
                stage="failed",
                message="Pipeline dừng do lỗi",
                error=error,
            )
        finally:
            self.tasks.pop(job_id, None)


manga_job_store = MangaJobStore()
