import time

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.repository import get_run_repository
from app.graph.workflow import build_manga_graph, get_manga_graph
from app.main import app
from app.services.jobs import manga_job_store
from tests.fakes import agent_bundle, critique_output


class FakeRepository:
    async def save(self, **kwargs) -> str:
        return "test-run-id"


def test_generate_manga_endpoint() -> None:
    graph = build_manga_graph(agents=agent_bundle(critique_output("accept")))
    app.dependency_overrides[get_manga_graph] = lambda: graph
    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="ollama", ollama_model="mock-model")
    app.dependency_overrides[get_run_repository] = lambda: FakeRepository()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/generate-manga",
                json={
                    "idea": "A magical pen changes the next day whenever its owner draws.",
                    "target_pages": 1,
                    "render_mode": "prompt_only",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accept"
    assert body["run_id"] == "test-run-id"
    assert body["model"] == "mock-model"
    assert body["story"]["pages"][0]["panels"][0]["panel_id"] == "p1_panel_1"
    assert body["generation"]["panels"][0]["panel_id"] == "p1_panel_1"
    assert body["render"]["backend"] == "prompt_only"


def test_background_job_reports_real_progress_and_result() -> None:
    graph = build_manga_graph(agents=agent_bundle(critique_output("accept")))
    app.dependency_overrides[get_manga_graph] = lambda: graph
    app.dependency_overrides[get_settings] = lambda: Settings(llm_provider="ollama", ollama_model="mock-model")
    app.dependency_overrides[get_run_repository] = lambda: FakeRepository()
    manga_job_store.jobs.clear()
    manga_job_store.tasks.clear()

    try:
        with TestClient(app) as client:
            created = client.post(
                "/manga-jobs",
                json={
                    "idea": "A magical pen changes the next day whenever its owner draws.",
                    "target_pages": 1,
                    "render_mode": "prompt_only",
                },
            )
            assert created.status_code == 202
            assert created.headers["content-type"] == "application/json; charset=utf-8"
            assert "Đã xếp hàng" in created.content.decode("utf-8")
            job_id = created.json()["job_id"]

            body = created.json()
            for _ in range(30):
                body = client.get(f"/manga-jobs/{job_id}").json()
                if body["state"] in {"completed", "failed"}:
                    break
                time.sleep(0.02)
    finally:
        app.dependency_overrides.clear()

    assert body["state"] == "completed"
    assert body["stage"] == "completed"
    assert body["progress"] == 100
    assert body["result"]["run_id"] == "test-run-id"
    assert body["result"]["story"]["pages"][0]["panels"][0]["panel_id"] == "p1_panel_1"
