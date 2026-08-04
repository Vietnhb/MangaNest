import asyncio
from functools import lru_cache
from typing import Protocol

from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import MangaRun, StoryEpisode, StorySeries
from app.schemas.api import GenerateMangaRequest, GenerateMangaResponse
from app.schemas.critique import CritiqueOutput
from app.schemas.generation import GenerationOutput
from app.schemas.layout import LayoutOutput
from app.schemas.render import RenderOutput
from app.schemas.memory import EpisodeApproveRequest, EpisodeDetail, EpisodeEditorUpdate, PanelPromptUpdate, RunProjectRef, SeriesCreate, SeriesDetail, SeriesPatch, SeriesSummary
from app.schemas.story import StoryOutput
from app.services.publishing import publish_episode


def _bubble_type(delivery: str) -> str:
    normalized = delivery.casefold()
    if any(token in normalized for token in ("thought", "inner", "suy nghĩ", "nội tâm")):
        return "thought"
    if any(token in normalized for token in ("whisper", "thì thầm", "quiet")):
        return "whisper"
    if any(token in normalized for token in ("shout", "yell", "scream", "hét")):
        return "shout"
    return "speech"


def _build_editor_payload(story: StoryOutput, layout: LayoutOutput) -> dict:
    pages: list[dict] = []
    for story_page in story.pages:
        layout_page = next((page for page in layout.pages if page.page_number == story_page.page_number), None)
        panels: list[dict] = []
        for story_panel in story_page.panels:
            layout_panel = next((panel for panel in (layout_page.panels if layout_page else []) if panel.panel_id == story_panel.panel_id), None)
            if layout_panel is None:
                continue
            bubbles: list[dict] = []
            lines = list(story_panel.dialogue)
            for index, line in enumerate(lines):
                bubbles.append({
                    "bubble_id": f"{story_panel.panel_id}_bubble_{index + 1}",
                    "line_id": line.line_id or f"{story_panel.panel_id}_line_{index + 1}",
                    "speaker": line.speaker,
                    "text": line.text,
                    "delivery": line.delivery,
                    "bubble_type": _bubble_type(line.delivery),
                    "box": {"x": max(0.05, 0.68 - index * 0.2), "y": 0.06 + index * 0.16, "width": 0.27, "height": 0.13},
                    "tail_x": max(0.1, 0.75 - index * 0.18), "tail_y": min(0.95, 0.3 + index * 0.15),
                    "reading_order": index + 1, "locked": False,
                })
            if story_panel.narration:
                bubbles.append({
                    "bubble_id": f"{story_panel.panel_id}_caption_1", "line_id": None, "speaker": None,
                    "text": story_panel.narration, "delivery": "narration", "bubble_type": "caption",
                    "box": {"x": 0.05, "y": 0.05, "width": 0.42, "height": 0.1},
                    "tail_x": None, "tail_y": None, "reading_order": len(bubbles) + 1, "locked": False,
                })
            for sfx_index, text in enumerate(story_panel.sound_effects, start=1):
                bubbles.append({
                    "bubble_id": f"{story_panel.panel_id}_sfx_{sfx_index}", "line_id": None,
                    "speaker": None, "text": text, "delivery": "sound effect", "bubble_type": "sfx",
                    "box": {"x": 0.06, "y": min(0.82, 0.7 + (sfx_index - 1) * 0.1), "width": 0.28, "height": 0.12},
                    "tail_x": None, "tail_y": None, "reading_order": len(bubbles) + 1, "locked": False,
                })
            panels.append({
                "panel_id": story_panel.panel_id,
                "box": layout_panel.box.model_dump(mode="json"),
                "reading_order": layout_panel.reading_order,
                "bubbles": bubbles,
                "artwork_locked": False, "panel_locked": False, "status": "draft",
            })
        pages.append({"page_number": story_page.page_number, "panels": panels})
    return {"pages": pages, "reading_direction": "right_to_left", "text_rendering": "separate_overlay"}


def _build_continuity_snapshot(story: StoryOutput, episode_number: int, previous: dict | None = None) -> dict:
    previous = previous or {}
    characters = dict(previous.get("characters", {}))
    for character in story.characters:
        key = character.character_id or character.name
        characters[key] = {
            "name": character.name, "appearance": character.appearance,
            "personality": character.personality, "speech_style": character.speech_style,
            "current_state": character.current_state, "motivation": character.motivation,
        }
    canon_facts = list(dict.fromkeys([*previous.get("canon_facts", []), *story.canon_facts, *story.continuity_updates]))
    return {
        "through_episode": episode_number,
        "characters": characters,
        "canon_facts": canon_facts,
        "unresolved_threads": story.unresolved_threads,
        "last_locations": list(dict.fromkeys(panel.setting for page in story.pages for panel in page.panels)),
        "last_page_hook": story.pages[-1].page_turn_hook,
        "episode_logline": story.logline,
    }


def _episode_detail(row: StoryEpisode, critique: dict | None = None) -> EpisodeDetail:
    return EpisodeDetail(
        id=row.id, series_id=row.series_id, run_id=row.run_id, episode_number=row.episode_number,
        title=row.title, status=row.status, revision=row.revision, story=row.story_payload,
        layout=row.layout_payload, generation=row.generation_payload, render=row.render_payload,
        editor=row.editor_payload, continuity_snapshot=row.continuity_snapshot,
        critique=critique,
        created_at=row.created_at, updated_at=row.updated_at,
    )


class RunRepository(Protocol):
    async def save(
        self,
        *,
        request: GenerateMangaRequest,
        model_name: str,
        revision_count: int,
        story: StoryOutput,
        layout: LayoutOutput,
        generation: GenerationOutput,
        render: RenderOutput,
        critique: CritiqueOutput,
    ) -> str: ...

    async def load_generation_context(self, series_id: str | None) -> dict | None: ...
    async def get_run_project_ref(self, run_id: str) -> RunProjectRef | None: ...
    async def create_series(self, payload: SeriesCreate) -> SeriesDetail: ...
    async def list_series(self) -> list[SeriesSummary]: ...
    async def get_series(self, series_id: str) -> SeriesDetail | None: ...
    async def patch_series(self, series_id: str, payload: SeriesPatch) -> SeriesDetail | None: ...
    async def get_episode(self, episode_id: str) -> EpisodeDetail | None: ...
    async def get_latest_series_result(self, series_id: str) -> GenerateMangaResponse | None: ...
    async def update_episode_editor(self, episode_id: str, payload: EpisodeEditorUpdate) -> EpisodeDetail | None: ...
    async def update_episode_render(self, episode_id: str, expected_revision: int, render: RenderOutput, critique: CritiqueOutput | None = None) -> EpisodeDetail | None: ...
    async def update_episode_panel_prompt(self, episode_id: str, panel_id: str, payload: PanelPromptUpdate) -> EpisodeDetail | None: ...
    async def approve_episode(self, episode_id: str, payload: EpisodeApproveRequest) -> EpisodeDetail | None: ...


class SqlAlchemyRunRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            self._schema_ready = True

    async def save(
        self,
        *,
        request: GenerateMangaRequest,
        model_name: str,
        revision_count: int,
        story: StoryOutput,
        layout: LayoutOutput,
        generation: GenerationOutput,
        render: RenderOutput,
        critique: CritiqueOutput,
    ) -> str:
        await self._ensure_schema()
        run = MangaRun(
            idea=request.idea,
            model_name=model_name,
            decision=critique.decision,
            overall_score=critique.overall_score,
            revision_count=revision_count,
            lora_eligible=critique.lora_training.eligible,
            request_payload=request.model_dump(mode="json"),
            story_payload=story.model_dump(mode="json"),
            layout_payload=layout.model_dump(mode="json"),
            generation_payload=generation.model_dump(mode="json"),
            render_payload=render.model_dump(mode="json"),
            critique_payload=critique.model_dump(mode="json"),
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.flush()
            episode = await self._capture_episode(session, run.id, request, story, layout, generation, render)
            await session.flush()
            published = await asyncio.to_thread(
                publish_episode,
                episode_id=episode.id,
                title=episode.title,
                episode_number=episode.episode_number,
                render=render,
                editor_payload=episode.editor_payload,
                output_dir=self.settings.render_output_dir,
            )
            episode.render_payload = published.model_dump(mode="json")
            run.render_payload = published.model_dump(mode="json")
            await session.commit()
        return run.id

    async def _capture_episode(self, session: AsyncSession, run_id: str, request: GenerateMangaRequest, story: StoryOutput, layout: LayoutOutput, generation: GenerationOutput, render: RenderOutput) -> StoryEpisode:
        now = datetime.now(timezone.utc)
        series = await session.get(StorySeries, request.series_id) if request.series_id else None
        if request.series_id and series is None:
            raise ValueError("Series not found")
        if series is None:
            series = StorySeries(
                title=story.title, premise=story.logline, visual_style=story.visual_tone,
                story_bible={
                    "characters": [item.model_dump(mode="json") for item in story.characters],
                    "world_rules": [], "dialogue_rules": [], "themes": story.themes,
                }, continuity_snapshot={}, updated_at=now,
            )
            session.add(series)
            await session.flush()
        maximum = await session.scalar(select(func.max(StoryEpisode.episode_number)).where(StoryEpisode.series_id == series.id))
        episode_number = request.episode_number or ((maximum or 0) + 1)
        existing = await session.scalar(select(StoryEpisode).where(StoryEpisode.series_id == series.id, StoryEpisode.episode_number == episode_number))
        if existing is not None:
            raise ValueError(f"Episode {episode_number} already exists in this series")
        snapshot = _build_continuity_snapshot(story, episode_number, series.continuity_snapshot)
        bible = dict(series.story_bible)
        known = {item.get("character_id") or item.get("name") for item in bible.get("characters", [])}
        bible["characters"] = [
            *bible.get("characters", []),
            *(item.model_dump(mode="json") for item in story.characters if (item.character_id or item.name) not in known),
        ]
        bible["themes"] = list(dict.fromkeys([*bible.get("themes", []), *story.themes]))
        series.story_bible = bible
        if not series.visual_style:
            series.visual_style = story.visual_tone
        episode = StoryEpisode(
            series_id=series.id, run_id=run_id, episode_number=episode_number, title=story.title,
            status="review", revision=1, story_payload=story.model_dump(mode="json"),
            layout_payload=layout.model_dump(mode="json"), generation_payload=generation.model_dump(mode="json"),
            render_payload=render.model_dump(mode="json"), editor_payload=_build_editor_payload(story, layout),
            continuity_snapshot=snapshot, updated_at=now,
        )
        session.add(episode)
        series.continuity_snapshot = snapshot
        series.updated_at = now
        series.version += 1
        return episode

    async def create_series(self, payload: SeriesCreate) -> SeriesDetail:
        await self._ensure_schema()
        series = StorySeries(
            title=payload.title, premise=payload.premise, visual_style=payload.visual_style,
            story_bible={"characters": [], "world_rules": payload.world_rules, "dialogue_rules": payload.dialogue_rules},
            continuity_snapshot={},
        )
        async with self.session_factory() as session:
            session.add(series); await session.commit(); await session.refresh(series)
            return self._series_detail(series, [])

    async def list_series(self) -> list[SeriesSummary]:
        await self._ensure_schema()
        async with self.session_factory() as session:
            rows = (await session.execute(
                select(StorySeries, func.count(StoryEpisode.id)).outerjoin(StoryEpisode).group_by(StorySeries.id).order_by(StorySeries.updated_at.desc())
            )).all()
            return [SeriesSummary(id=s.id, title=s.title, premise=s.premise, visual_style=s.visual_style, version=s.version, episode_count=count, updated_at=s.updated_at) for s, count in rows]

    async def get_series(self, series_id: str) -> SeriesDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            series = await session.get(StorySeries, series_id)
            if series is None: return None
            episodes = list((await session.scalars(select(StoryEpisode).where(StoryEpisode.series_id == series_id).order_by(StoryEpisode.episode_number))).all())
            return self._series_detail(series, episodes)

    def _series_detail(self, series: StorySeries, episodes: list[StoryEpisode]) -> SeriesDetail:
        return SeriesDetail(
            id=series.id, title=series.title, premise=series.premise, visual_style=series.visual_style,
            version=series.version, episode_count=len(episodes), updated_at=series.updated_at,
            story_bible=series.story_bible, continuity_snapshot=series.continuity_snapshot,
            episodes=[_episode_detail(item) for item in episodes],
        )

    async def patch_series(self, series_id: str, payload: SeriesPatch) -> SeriesDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            series = await session.get(StorySeries, series_id)
            if series is None: return None
            if series.version != payload.expected_version: raise RuntimeError("version_conflict")
            changes = payload.model_dump(exclude={"expected_version"}, exclude_none=True)
            bible = dict(series.story_bible)
            for key in ("world_rules", "dialogue_rules"):
                if key in changes: bible[key] = changes.pop(key)
            for key, value in changes.items(): setattr(series, key, value)
            series.story_bible = bible; series.version += 1; series.updated_at = datetime.now(timezone.utc)
            await session.commit()
        return await self.get_series(series_id)

    async def get_episode(self, episode_id: str) -> EpisodeDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.get(StoryEpisode, episode_id)
            if row is None: return None
            run = await session.get(MangaRun, row.run_id) if row.run_id else None
            return _episode_detail(row, run.critique_payload if run else None)

    async def get_latest_series_result(self, series_id: str) -> GenerateMangaResponse | None:
        """Rehydrate the latest production so creators can resume after a restart."""
        await self._ensure_schema()
        async with self.session_factory() as session:
            episode = await session.scalar(
                select(StoryEpisode)
                .where(StoryEpisode.series_id == series_id)
                .order_by(StoryEpisode.episode_number.desc())
                .limit(1)
            )
            if episode is None or episode.run_id is None:
                return None
            run = await session.get(MangaRun, episode.run_id)
            if run is None:
                return None
            return GenerateMangaResponse(
                run_id=run.id,
                status=run.decision,
                model=run.model_name,
                revision_count=run.revision_count,
                story=StoryOutput.model_validate(episode.story_payload),
                layout=LayoutOutput.model_validate(episode.layout_payload),
                generation=GenerationOutput.model_validate(episode.generation_payload),
                render=RenderOutput.model_validate(episode.render_payload),
                critique=CritiqueOutput.model_validate(run.critique_payload),
                series_id=episode.series_id,
                episode_id=episode.id,
                episode_number=episode.episode_number,
            )

    async def update_episode_editor(self, episode_id: str, payload: EpisodeEditorUpdate) -> EpisodeDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.get(StoryEpisode, episode_id)
            if row is None: return None
            if row.status == "locked": raise PermissionError("episode_locked")
            if row.revision != payload.expected_revision: raise RuntimeError("revision_conflict")
            row.editor_payload = {"pages": [page.model_dump(mode="json") for page in payload.pages], "reading_direction": "right_to_left", "text_rendering": "separate_overlay"}
            row.status = payload.status if payload.status in {"draft", "review"} else "draft"
            row.revision += 1; row.updated_at = datetime.now(timezone.utc)
            current_render = RenderOutput.model_validate(row.render_payload)
            if any(panel.status == "completed" and panel.image_path for panel in current_render.panels):
                published = await asyncio.to_thread(
                    publish_episode,
                    episode_id=row.id,
                    title=row.title,
                    episode_number=row.episode_number,
                    render=current_render,
                    editor_payload=row.editor_payload,
                    output_dir=self.settings.render_output_dir,
                    allow_export=False,
                )
                row.render_payload = published.model_dump(mode="json")
                if row.run_id:
                    run = await session.get(MangaRun, row.run_id)
                    if run is not None: run.render_payload = row.render_payload
            await session.commit(); await session.refresh(row)
            return _episode_detail(row)

    async def update_episode_render(
        self, episode_id: str, expected_revision: int, render: RenderOutput,
        critique: CritiqueOutput | None = None,
    ) -> EpisodeDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.get(StoryEpisode, episode_id)
            if row is None: return None
            if row.status == "locked": raise PermissionError("episode_locked")
            if row.revision != expected_revision: raise RuntimeError("revision_conflict")
            payload = render.model_dump(mode="json")
            row.render_payload = payload
            row.status = "review"
            row.revision += 1; row.updated_at = datetime.now(timezone.utc)
            critique_payload = critique.model_dump(mode="json") if critique else None
            if row.run_id:
                run = await session.get(MangaRun, row.run_id)
                if run is not None:
                    run.render_payload = payload
                    if critique_payload is not None:
                        run.critique_payload = critique_payload
                        run.overall_score = critique.overall_score
                        run.decision = critique.decision
            await session.commit(); await session.refresh(row)
            return _episode_detail(row, critique_payload)

    async def update_episode_panel_prompt(
        self, episode_id: str, panel_id: str, payload: PanelPromptUpdate
    ) -> EpisodeDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.get(StoryEpisode, episode_id)
            if row is None: return None
            if row.status == "locked": raise PermissionError("episode_locked")
            if row.revision != payload.expected_revision: raise RuntimeError("revision_conflict")
            generation = GenerationOutput.model_validate(row.generation_payload)
            found = False
            panels = []
            for panel in generation.panels:
                if panel.panel_id != panel_id:
                    panels.append(panel)
                    continue
                found = True
                panels.append(panel.model_copy(update={
                    "positive_prompt": payload.positive_prompt,
                    "negative_prompt": payload.negative_prompt,
                    "composition_control": payload.composition_control,
                    **({"identity_mode": payload.identity_mode} if payload.identity_mode is not None else {}),
                    **({"identity_strength": payload.identity_strength} if "identity_strength" in payload.model_fields_set else {}),
                }))
            if not found: raise ValueError("panel_not_found")
            updated = generation.model_copy(update={"panels": panels})
            row.generation_payload = updated.model_dump(mode="json")
            row.status = "draft"
            row.revision += 1; row.updated_at = datetime.now(timezone.utc)
            if row.run_id:
                run = await session.get(MangaRun, row.run_id)
                if run is not None: run.generation_payload = row.generation_payload
            await session.commit(); await session.refresh(row)
            return _episode_detail(row)

    async def approve_episode(
        self, episode_id: str, payload: EpisodeApproveRequest
    ) -> EpisodeDetail | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.get(StoryEpisode, episode_id)
            if row is None: return None
            if row.revision != payload.expected_revision: raise RuntimeError("revision_conflict")
            if row.status == "locked": raise PermissionError("episode_locked")
            if row.status != "review": raise ValueError("fresh_review_required")
            run = await session.get(MangaRun, row.run_id) if row.run_id else None
            if run is None: raise ValueError("critique_missing")
            critique = CritiqueOutput.model_validate(run.critique_payload)
            if critique.overall_score < self.settings.quality_approval_threshold:
                raise ValueError("quality_below_threshold")
            if any(item.score < self.settings.quality_panel_threshold for item in critique.panel_critiques):
                raise ValueError("panel_below_threshold")
            editor = dict(row.editor_payload)
            editor["pages"] = [
                {**page, "panels": [{**panel, "status": "approved"} for panel in page["panels"]]}
                for page in editor.get("pages", [])
            ]
            rendered = await asyncio.to_thread(
                publish_episode,
                episode_id=row.id,
                title=row.title,
                episode_number=row.episode_number,
                render=RenderOutput.model_validate(row.render_payload),
                editor_payload=editor,
                output_dir=self.settings.render_output_dir,
                allow_export=True,
            )
            row.editor_payload = editor
            row.render_payload = rendered.model_dump(mode="json")
            row.status = "approved"
            row.revision += 1; row.updated_at = datetime.now(timezone.utc)
            run.render_payload = row.render_payload
            await session.commit(); await session.refresh(row)
            return _episode_detail(row, run.critique_payload)

    async def get_run_project_ref(self, run_id: str) -> RunProjectRef | None:
        await self._ensure_schema()
        async with self.session_factory() as session:
            row = await session.scalar(select(StoryEpisode).where(StoryEpisode.run_id == run_id))
            return RunProjectRef(run_id=run_id, series_id=row.series_id, episode_id=row.id, episode_number=row.episode_number) if row else None

    async def load_generation_context(self, series_id: str | None) -> dict | None:
        if not series_id: return None
        detail = await self.get_series(series_id)
        if detail is None: raise ValueError("Series not found")
        previous = detail.episodes[-1] if detail.episodes else None
        return {
            "series_id": detail.id, "story_bible": detail.story_bible,
            "continuity_snapshot": detail.continuity_snapshot,
            "previous_episode": previous.model_dump(mode="json") if previous else None,
            "existing_episode_numbers": [item.episode_number for item in detail.episodes],
        }


@lru_cache
def get_run_repository() -> SqlAlchemyRunRepository:
    return SqlAlchemyRunRepository(get_settings())
