import pytest
from dataclasses import replace

from app.graph.workflow import build_manga_graph
from tests.fakes import agent_bundle, critique_output


class InvalidJsonCritic:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, user_payload: str):
        self.calls += 1
        raise ValueError("Invalid json output")


def initial_state(max_revisions: int = 2) -> dict:
    return {
        "idea": "A magical pen changes the next day whenever its owner draws.",
        "target_pages": 1,
        "genre": ["fantasy"],
        "audience": "teen",
        "manga_style": "black-and-white manga",
        "max_revisions": max_revisions,
        "revision_count": 0,
        "render_mode": "prompt_only",
    }


@pytest.mark.asyncio
async def test_graph_runs_all_four_agents() -> None:
    agents = agent_bundle(critique_output("accept"))
    result = await build_manga_graph(agents=agents).ainvoke(initial_state())

    assert result["critique"].decision == "accept"
    assert result["revision_count"] == 0
    assert agents.story.calls == 1
    assert agents.layout.calls == 1
    assert agents.generation.calls == 1
    assert agents.critique.calls == 1
    panel = result["generation"].panels[0]
    assert "short black bob" in panel.positive_prompt
    assert panel.character_consistency[0].startswith("char_")


@pytest.mark.asyncio
async def test_critique_can_request_one_generation_revision() -> None:
    agents = agent_bundle(critique_output("regenerate"), critique_output("accept"))
    result = await build_manga_graph(agents=agents).ainvoke(initial_state(max_revisions=1))

    assert result["critique"].decision == "accept"
    assert result["revision_count"] == 1
    assert agents.story.calls == 1
    assert agents.layout.calls == 1
    assert agents.generation.calls == 2
    assert agents.critique.calls == 2


@pytest.mark.asyncio
async def test_revision_limit_stops_regeneration_loop() -> None:
    agents = agent_bundle(critique_output("regenerate"))
    result = await build_manga_graph(agents=agents).ainvoke(initial_state(max_revisions=0))

    assert result["critique"].decision == "accept_with_warnings"
    assert result["revision_count"] == 0
    assert agents.generation.calls == 1


@pytest.mark.asyncio
async def test_invalid_critique_never_discards_completed_product() -> None:
    base = agent_bundle(critique_output("accept"))
    broken = InvalidJsonCritic()
    agents = replace(base, critique=broken)

    state = initial_state()
    state["render_mode"] = "mock"
    result = await build_manga_graph(agents=agents).ainvoke(state)

    assert result["critique"].decision == "accept_with_warnings"
    assert result["critique"].overall_score == 7.0
    assert result["critique"].lora_training.eligible is False
    assert result["render"].panels[0].status == "completed"
    assert broken.calls == 2
