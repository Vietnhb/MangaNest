import pytest

from app.core.config import Settings
from PIL import Image

from app.services.rendering import (
    RenderingService,
    _bounded_dimensions,
    _compile_animagine_negative,
    _compile_animagine_positive,
    _normalize_manga_art,
    _technical_candidate_score,
)
from tests.fakes import generation_output


def test_sdxl_bucket_normalization() -> None:
    assert _bounded_dimensions(512, 360, 1216, 1216) == (1216, 832)
    assert _bounded_dimensions(512, 900, 1216, 1216) == (832, 1216)
    assert _bounded_dimensions(512, 512, 1216, 1216) == (1024, 1024)


def test_manga_postprocess_removes_color_without_changing_dimensions(tmp_path) -> None:
    path = tmp_path / "panel.png"
    Image.new("RGB", (64, 32), (20, 180, 240)).save(path)
    _normalize_manga_art(path)
    with Image.open(path) as result:
        assert result.mode == "L"
        assert result.size == (64, 32)


def test_candidate_score_rejects_flat_image(tmp_path) -> None:
    flat = tmp_path / "flat.png"
    detailed = tmp_path / "detailed.png"
    Image.new("L", (128, 128), 255).save(flat)
    image = Image.new("L", (128, 128), 255)
    for x in range(0, 128, 8):
        for y in range(128):
            image.putpixel((x, y), 0)
    image.save(detailed)
    assert _technical_candidate_score(detailed) > _technical_candidate_score(flat)


def test_animagine_compiler_orders_identity_and_bounds_accumulated_tags() -> None:
    generation = generation_output()
    panel = generation.panels[0].model_copy(update={
        "positive_prompt": "1girl, solo, seated, repairing a watch, " + ", ".join(f"detail {i}" for i in range(100)),
        "negative_prompt": "text, text, watermark, unrelated old correction",
        "character_consistency": ["Aki, short black bob, round glasses"],
    })
    positive = _compile_animagine_positive(panel, generation)
    negative = _compile_animagine_negative(panel, generation)
    tags = positive.split(", ")

    assert tags[:2] == ["1girl", "solo"]
    assert "Aki" in tags[:8]
    assert len(tags) <= 64
    assert negative.casefold().count("text") == 1


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
    assert workflow["11"]["inputs"]["preset"] == "PLUS FACE (portraits)"
    assert workflow["12"]["class_type"] == "IPAdapterAdvanced"
    assert workflow["12"]["inputs"]["weight"] == 0.7
    assert workflow["5"]["inputs"]["model"] == ["12", 0]
    assert workflow["4"]["inputs"]["batch_size"] == 2
    positive = workflow["2"]["inputs"]["text"]
    assert positive.index("short black bob") < positive.index("single uninterrupted illustration")


def test_faceid_remains_available_for_photographic_references(tmp_path) -> None:
    renderer = RenderingService(
        Settings(render_output_dir=str(tmp_path), comfyui_faceid_enabled=True)
    )
    generation = generation_output()
    workflow = renderer._workflow(
        generation.panels[0], generation, 42, 640, 896, 1, "identity/photo.png"
    )

    assert workflow["11"]["class_type"] == "IPAdapterUnifiedLoaderFaceID"
    assert workflow["11"]["inputs"]["preset"] == "FACEID PLUS V2"
    assert workflow["12"]["class_type"] == "IPAdapterFaceID"
    assert workflow["12"]["inputs"]["weight_faceidv2"] == 1.0


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
    assert renderer._identity_conditioning_profile(wide) is None

    forced_wide = wide.model_copy(update={"identity_mode": "reference"})
    assert renderer._identity_conditioning_profile(forced_wide) == (0.25, 0.55)

    forced = panel.model_copy(update={"identity_mode": "reference", "identity_strength": 0.33})
    assert renderer._identity_conditioning_profile(forced) == (0.33, 0.65)


def test_identity_reference_view_matches_panel_camera(tmp_path) -> None:
    renderer = RenderingService(Settings(render_output_dir=str(tmp_path)))
    panel = generation_output().panels[0]
    assert renderer._identity_reference_view(panel.model_copy(update={
        "positive_prompt": "close-up front view portrait",
    })) == "front"
    assert renderer._identity_reference_view(panel.model_copy(update={
        "positive_prompt": "character profile from the side",
    })) == "profile"
    assert renderer._identity_reference_view(panel.model_copy(update={
        "positive_prompt": "full body standing pose",
    })) == "full_body"


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
