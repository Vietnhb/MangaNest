from pathlib import Path

from PIL import Image


def _groups(indices: list[int]) -> int:
    if not indices:
        return 0
    groups = 1
    for previous, current in zip(indices, indices[1:]):
        if current > previous + 1:
            groups += 1
    return groups


def detect_embedded_panel_grid(image_path: str) -> bool:
    """Detect strong interior dividers that indicate a generated comic-page collage."""
    path = Path(image_path)
    if not path.exists():
        return False
    with Image.open(path) as source:
        image = source.convert("L")
        image.thumbnail((256, 256))
        width, height = image.size
        pixels = image.load()
        margin_x = max(3, width // 18)
        margin_y = max(3, height // 18)
        dark = 42
        # Interior comic dividers are nearly uninterrupted. A lower ratio
        # incorrectly classifies windows, desks and heavy manga shadows as grids.
        divider_coverage = 0.97
        horizontal = [
            y for y in range(margin_y, height - margin_y)
            if sum(pixels[x, y] < dark for x in range(width)) / width >= divider_coverage
        ]
        vertical = [
            x for x in range(margin_x, width - margin_x)
            if sum(pixels[x, y] < dark for y in range(height)) / height >= divider_coverage
        ]
    return _groups(horizontal) >= 2 or _groups(vertical) >= 2
