from PIL import Image, ImageDraw

from app.services.publishing import _fit_wrapped_text


def test_vietnamese_dialogue_is_fitted_without_vertical_clipping() -> None:
    draw = ImageDraw.Draw(Image.new("RGB", (300, 160), "white"))
    _, lines, line_height = _fit_wrapped_text(
        draw,
        "Đến lúc bước tiếp rồi.",
        max_width=120,
        max_height=72,
        preferred_size=28,
    )

    assert " ".join(lines) == "Đến lúc bước tiếp rồi."
    assert len(lines) * line_height <= 72
