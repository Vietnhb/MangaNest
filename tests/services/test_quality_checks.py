from PIL import Image, ImageDraw

from app.services.quality_checks import detect_embedded_panel_grid


def test_detects_generated_comic_grid(tmp_path) -> None:
    path = tmp_path / "grid.png"
    image = Image.new("L", (256, 256), 245)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 70, 255, 82), fill=0)
    draw.rectangle((0, 166, 255, 178), fill=0)
    image.save(path)
    assert detect_embedded_panel_grid(str(path)) is True


def test_accepts_single_scene_without_dividers(tmp_path) -> None:
    path = tmp_path / "scene.png"
    image = Image.new("L", (256, 256), 235)
    draw = ImageDraw.Draw(image)
    draw.ellipse((75, 35, 180, 150), fill=30)
    draw.polygon([(55, 255), (110, 120), (205, 255)], fill=70)
    image.save(path)
    assert detect_embedded_panel_grid(str(path)) is False


def test_accepts_heavy_architectural_lines_that_do_not_span_the_image(tmp_path) -> None:
    path = tmp_path / "architecture.png"
    image = Image.new("L", (256, 256), 235)
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 30, 238, 42), fill=0)
    draw.rectangle((20, 170, 245, 184), fill=0)
    draw.rectangle((35, 0, 48, 220), fill=0)
    image.save(path)
    assert detect_embedded_panel_grid(str(path)) is False
