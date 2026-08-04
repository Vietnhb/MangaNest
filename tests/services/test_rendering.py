import pytest

from app.core.config import Settings
from app.services.rendering import RenderingService, _bounded_dimensions
from tests.fakes import generation_output


def test_sdxl_bucket_normalization() -> None:
    assert _bounded_dimensions(512, 360, 768, 896) == (768, 512)
    assert _bounded_dimensions(512, 900, 768, 896) == (576, 896)
    assert _bounded_dimensions(512, 512, 768, 896) == (640, 640)


def test_ipadapter_workflow_conditions_sampler_on_identity_reference(tmp_path) -> None:
    renderer = RenderingService(
        Settings(
            render_output_dir=str(tmp_path),
            comfyui_ipadapter_weight=0.7,
            comfyui_ipadapter_end_at=0.8,
        )
    )
    generation = generation_output()
    workflow = renderer._workflow(
        generation.panels[0], generation, 42, 640, 896, 1, "identity/reference.png"
    )

    assert workflow["10"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "identity/reference.png"},
    }
    assert workflow["11"]["class_type"] == "IPAdapterUnifiedLoader"
    assert workflow["12"]["class_type"] == "IPAdapterAdvanced"
    assert workflow["12"]["inputs"]["weight"] == 0.7
    assert workflow["5"]["inputs"]["model"] == ["12", 0]


def test_adaptive_identity_skips_multi_subject_reflection_and_softens_wide_shots(tmp_path) -> None:
    renderer = RenderingService(Settings(render_output_dir=str(tmp_path)))
    panel = generation_output().panels[0].model_copy(update={
        "character_consistency": ["Linh, black bob hair, dark scarf"],
        "positive_prompt": "Linh and one reflected adult man, two distinct faces",
        "composition_control": "medium shot",
    })
    assert renderer._identity_conditioning_profile(panel) is None

    wide = panel.model_copy(update={
        "positive_prompt": "Linh alone at a workbench",
        "composition_control": "wide establishing shot",
    })
    assert renderer._identity_conditioning_profile(wide) == (0.2, 0.5)

    forced = panel.model_copy(update={"identity_mode": "reference", "identity_strength": 0.33})
    assert renderer._identity_conditioning_profile(forced) == (0.33, 0.65)


@pytest.mark.asyncio
async def test_mock_renderer_creates_viewable_panel(tmp_path) -> None:
    renderer = RenderingService(
        Settings(
            render_output_dir=str(tmp_path),
            render_max_width=768,
            render_max_height=896,
        )
    )

    result = await renderer.render(generation_output(), 0, "mock")

    assert result.backend == "mock"
    assert result.panels[0].status == "completed"
    assert result.panels[0].image_url.startswith("/outputs/mock/")
    assert result.panels[0].image_path is not None
