import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import MangaRun
from app.db.repository import SqlAlchemyRunRepository
from app.schemas.api import GenerateMangaRequest
from app.schemas.memory import EpisodeEditorUpdate
from tests.fakes import (
    critique_output,
    generation_output,
    layout_output,
    render_output,
    story_output,
)


@pytest.mark.asyncio
async def test_repository_persists_lora_candidate_metadata(tmp_path) -> None:
    database_path = (tmp_path / "runs.db").as_posix()
    repository = SqlAlchemyRunRepository(
        Settings(database_url=f"sqlite+aiosqlite:///{database_path}")
    )
    critique = critique_output("accept")

    run_id = await repository.save(
        request=GenerateMangaRequest(
            idea="A magical pen changes the next day whenever its owner draws.",
            target_pages=1,
        ),
        model_name="mock-model",
        revision_count=0,
        story=story_output(),
        layout=layout_output(),
        generation=generation_output(),
        render=render_output(),
        critique=critique,
    )

    async with repository.session_factory() as session:
        stored = await session.scalar(select(MangaRun).where(MangaRun.id == run_id))

    assert stored is not None
    assert stored.lora_eligible is True
    assert stored.critique_payload["lora_training"]["caption_tags"]
    project = await repository.get_run_project_ref(run_id)
    assert project is not None
    assert project.episode_number == 1
    series = await repository.get_series(project.series_id)
    assert series is not None
    assert series.episode_count == 1
    assert series.continuity_snapshot["through_episode"] == 1
    assert series.story_bible["characters"][0]["name"] == "Aki"
    resumed = await repository.get_latest_series_result(project.series_id)
    assert resumed is not None
    assert resumed.run_id == run_id
    assert resumed.episode_id == project.episode_id
    assert resumed.story.title == "The Last Ink"
    assert resumed.critique.overall_score == critique.overall_score
    await repository.engine.dispose()


@pytest.mark.asyncio
async def test_episode_editor_is_versioned_and_dialogue_is_separate_from_artwork(tmp_path) -> None:
    database_path = (tmp_path / "editor.db").as_posix()
    repository = SqlAlchemyRunRepository(Settings(database_url=f"sqlite+aiosqlite:///{database_path}"))
    run_id = await repository.save(
        request=GenerateMangaRequest(idea="A magical pen changes the next day whenever its owner draws.", target_pages=1),
        model_name="mock-model", revision_count=0, story=story_output(), layout=layout_output(),
        generation=generation_output(), render=render_output(), critique=critique_output("accept"),
    )
    project = await repository.get_run_project_ref(run_id)
    episode = await repository.get_episode(project.episode_id)
    pages = episode.editor["pages"]
    panel = pages[0]["panels"][0]
    panel["bubbles"].append({
        "bubble_id": "p1_panel_1_bubble_manual", "speaker": "Aki", "text": "I remember.",
        "delivery": "quiet", "bubble_type": "speech",
        "box": {"x": .6, "y": .1, "width": .3, "height": .15},
            "reading_order": max((item["reading_order"] for item in panel["bubbles"]), default=0) + 1,
            "locked": True,
    })
    updated = await repository.update_episode_editor(
        episode.id, EpisodeEditorUpdate(expected_revision=episode.revision, pages=pages, status="review")
    )
    assert updated.revision == 2
    assert updated.status == "review"
    assert updated.editor["text_rendering"] == "separate_overlay"
    assert any(
        bubble["text"] == "I remember."
        for bubble in updated.editor["pages"][0]["panels"][0]["bubbles"]
    )
    with pytest.raises(RuntimeError, match="revision_conflict"):
        await repository.update_episode_editor(
            episode.id, EpisodeEditorUpdate(expected_revision=1, pages=pages)
        )
    await repository.engine.dispose()
