import json
import re
import zipfile
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.schemas.render import PageRender, PublicationBundle, RenderOutput


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
PAGE_MARGIN = 34


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return slug[:80] or "manga"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    path = next((item for item in candidates if item.exists()), None)
    return ImageFont.truetype(str(path), size=size) if path else ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw, text: str, *, max_width: int, max_height: int,
    preferred_size: int, bold: bool = False,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    """Fit complete Unicode text inside a layer instead of clipping its last lines."""
    for size in range(preferred_size, 11, -1):
        font = _font(size, bold=bold)
        lines = _wrap_text(draw, text, font, max_width)
        line_height = size + 3
        if lines and len(lines) * line_height <= max_height:
            return font, lines, line_height
    font = _font(12, bold=bold)
    return font, _wrap_text(draw, text, font, max_width), 15


def _draw_bubble(draw: ImageDraw.ImageDraw, bubble: dict[str, Any], panel_rect: tuple[int, int, int, int]) -> None:
    panel_x, panel_y, panel_w, panel_h = panel_rect
    box = bubble["box"]
    x = panel_x + round(box["x"] * panel_w)
    y = panel_y + round(box["y"] * panel_h)
    width = max(72, round(box["width"] * panel_w))
    height = max(54, round(box["height"] * panel_h))
    x = min(x, panel_x + panel_w - width)
    y = min(y, panel_y + panel_h - height)
    kind = bubble.get("bubble_type", "speech")
    text = bubble.get("text", "").strip()
    padding = max(8, width // 18)
    if kind == "sfx":
        body_font, lines, line_height = _fit_wrapped_text(
            draw, text, max_width=width - padding * 2, max_height=height - padding * 2,
            preferred_size=min(34, max(16, height // 3)), bold=True,
        )
        cursor_y = y + max(padding, (height - len(lines) * line_height) // 2)
        for line in lines:
            line_box = draw.textbbox((0, 0), line, font=body_font)
            line_width = line_box[2] - line_box[0]
            draw.text(
                (x + (width - line_width) // 2, cursor_y), line, fill="black",
                font=body_font, stroke_width=2, stroke_fill="white",
            )
            cursor_y += line_height
        return

    rect = (x, y, x + width, y + height)
    border_width = 5 if kind == "shout" else 3
    if kind != "caption" and bubble.get("tail_x") is not None and bubble.get("tail_y") is not None:
        target_x = panel_x + round(bubble["tail_x"] * panel_w)
        target_y = panel_y + round(bubble["tail_y"] * panel_h)
        base_y = y + height - 7
        center_x = x + width // 2
        draw.polygon(
            [(center_x - 10, base_y), (center_x + 10, base_y), (target_x, target_y)],
            fill="white", outline="black",
        )
    if kind == "caption":
        draw.rounded_rectangle(rect, radius=5, fill="white", outline="black", width=border_width)
    else:
        draw.ellipse(rect, fill="white", outline="black", width=border_width)

    body_font, lines, line_height = _fit_wrapped_text(
        draw, text, max_width=width - padding * 2, max_height=height - padding * 2,
        preferred_size=min(30, max(16, height // 4)), bold=kind == "shout",
    )
    total_height = len(lines) * line_height
    cursor_y = y + max(padding, (height - total_height) // 2)
    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=body_font)
        line_width = line_box[2] - line_box[0]
        draw.text((x + (width - line_width) // 2, cursor_y), line, fill="black", font=body_font)
        cursor_y += line_height


def _compose_page(page: dict[str, Any], panels_by_id: dict[str, Any], destination: Path) -> PageRender:
    canvas_image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(canvas_image)
    for panel in sorted(page["panels"], key=lambda item: item["reading_order"]):
        source = panels_by_id.get(panel["panel_id"])
        if source is None or not source.image_path or not Path(source.image_path).exists():
            continue
        box = panel["box"]
        x = PAGE_MARGIN + round(box["x"] * (PAGE_WIDTH - PAGE_MARGIN * 2))
        y = PAGE_MARGIN + round(box["y"] * (PAGE_HEIGHT - PAGE_MARGIN * 2))
        width = round(box["width"] * (PAGE_WIDTH - PAGE_MARGIN * 2))
        height = round(box["height"] * (PAGE_HEIGHT - PAGE_MARGIN * 2))
        with Image.open(source.image_path) as source_image:
            fitted = ImageOps.fit(source_image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
            canvas_image.paste(fitted, (x, y))
        draw.rectangle((x, y, x + width, y + height), outline="black", width=6)
        for bubble in sorted(panel.get("bubbles", []), key=lambda item: item["reading_order"]):
            _draw_bubble(draw, bubble, (x, y, width, height))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas_image.save(destination, optimize=True)
    return PageRender(
        page_number=page["page_number"], image_path=str(destination.resolve()),
        image_url=f"/outputs/publications/{destination.parent.name}/{destination.name}",
        width=PAGE_WIDTH, height=PAGE_HEIGHT,
    )


def publish_episode(
    *, episode_id: str, title: str, episode_number: int, render: RenderOutput,
    editor_payload: dict[str, Any], output_dir: str, allow_export: bool = False,
) -> RenderOutput:
    """Compose finished panels and dialogue into PNG pages, PDF, CBZ, and a manifest."""
    if not render.panels or not any(panel.status == "completed" and panel.image_path for panel in render.panels):
        return render
    publication_dir = Path(output_dir) / "publications" / episode_id
    publication_dir.mkdir(parents=True, exist_ok=True)
    panels_by_id = {panel.panel_id: panel for panel in render.panels}
    page_renders = [
        _compose_page(page, panels_by_id, publication_dir / f"page_{page['page_number']:03d}.png")
        for page in sorted(editor_payload.get("pages", []), key=lambda item: item["page_number"])
    ]
    page_renders = [page for page in page_renders if Path(page.image_path).exists()]
    if not page_renders:
        return render

    if not allow_export:
        return render.model_copy(update={"pages": page_renders, "publication": None})

    slug = _safe_slug(title)
    pdf_path = publication_dir / f"{slug}-episode-{episode_number}.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    pdf.setTitle(title)
    for page in page_renders:
        pdf.drawImage(ImageReader(page.image_path), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
        pdf.showPage()
    pdf.save()

    cbz_path = publication_dir / f"{slug}-episode-{episode_number}.cbz"
    comic_info = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        f"<ComicInfo><Title>{escape(title)}</Title><Number>{episode_number}</Number>"
        f"<PageCount>{len(page_renders)}</PageCount><Manga>YesAndRightToLeft</Manga></ComicInfo>"
    )
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ComicInfo.xml", comic_info)
        for page in page_renders:
            archive.write(page.image_path, Path(page.image_path).name)

    manifest_path = publication_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "episode_id": episode_id, "title": title, "episode_number": episode_number,
        "reading_direction": "right_to_left", "text_rendering": "deterministic_overlay",
        "pages": [page.model_dump(mode="json") for page in page_renders],
        "panel_count": len(render.panels), "render_backend": render.backend,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    base_url = f"/outputs/publications/{episode_id}"
    return render.model_copy(update={
        "pages": page_renders,
        "publication": PublicationBundle(
            pdf_path=str(pdf_path.resolve()), pdf_url=f"{base_url}/{pdf_path.name}",
            cbz_path=str(cbz_path.resolve()), cbz_url=f"{base_url}/{cbz_path.name}",
            manifest_path=str(manifest_path.resolve()), manifest_url=f"{base_url}/{manifest_path.name}",
        ),
    })
