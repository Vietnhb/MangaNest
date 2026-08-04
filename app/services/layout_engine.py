from app.schemas.layout import LayoutOutput, NormalizedBox, PageLayout, PanelLayout
from app.schemas.story import StoryOutput


TEMPLATES: dict[int, list[tuple[float, float, float, float]]] = {
    1: [(0.035, 0.025, 0.93, 0.95)],
    2: [(0.035, 0.025, 0.93, 0.455), (0.035, 0.51, 0.93, 0.465)],
    3: [(0.035, 0.025, 0.93, 0.44), (0.51, 0.495, 0.455, 0.48), (0.035, 0.495, 0.445, 0.48)],
    4: [(0.51, 0.025, 0.455, 0.455), (0.035, 0.025, 0.445, 0.455), (0.51, 0.51, 0.455, 0.465), (0.035, 0.51, 0.445, 0.465)],
    5: [(0.035, 0.025, 0.93, 0.30), (0.51, 0.355, 0.455, 0.29), (0.035, 0.355, 0.445, 0.29), (0.51, 0.675, 0.455, 0.30), (0.035, 0.675, 0.445, 0.30)],
    6: [(0.51, 0.025, 0.455, 0.29), (0.035, 0.025, 0.445, 0.29), (0.51, 0.345, 0.455, 0.30), (0.035, 0.345, 0.445, 0.30), (0.51, 0.675, 0.455, 0.30), (0.035, 0.675, 0.445, 0.30)],
    7: [(0.51, 0.025, 0.455, 0.28), (0.035, 0.025, 0.445, 0.28), (0.51, 0.335, 0.455, 0.28), (0.035, 0.335, 0.445, 0.28), (0.68, 0.645, 0.285, 0.33), (0.3575, 0.645, 0.2925, 0.33), (0.035, 0.645, 0.2925, 0.33)],
}


def _grid_boxes(count: int) -> list[tuple[float, float, float, float]]:
    columns = 3
    rows = (count + columns - 1) // columns
    gap = 0.025
    width = (0.93 - gap * (columns - 1)) / columns
    height = (0.95 - gap * (rows - 1)) / rows
    boxes = []
    for index in range(count):
        row = index // columns
        rtl_column = columns - 1 - (index % columns)
        boxes.append(
            (
                0.035 + rtl_column * (width + gap),
                0.025 + row * (height + gap),
                width,
                height,
            )
        )
    return boxes


def build_professional_layout(story: StoryOutput) -> LayoutOutput:
    """Create safe right-to-left manga geometry without asking an LLM for math."""

    pages: list[PageLayout] = []
    for story_page in story.pages:
        boxes = TEMPLATES.get(len(story_page.panels)) or _grid_boxes(
            len(story_page.panels)
        )
        panels: list[PanelLayout] = []
        for index, (story_panel, values) in enumerate(
            zip(story_page.panels, boxes, strict=True)
        ):
            x, y, width, height = values
            has_dialogue = bool(story_panel.dialogue or story_panel.narration)
            panels.append(
                PanelLayout(
                    panel_id=story_panel.panel_id,
                    reading_order=index + 1,
                    box=NormalizedBox(x=x, y=y, width=width, height=height),
                    shape="horizontal" if width / height > 1.7 else "rectangle",
                    border="thick" if index == 0 else "standard",
                    bleed=index == 0 and len(story_page.panels) <= 3,
                    focal_weight="major" if index == 0 else "normal",
                    composition_notes=(
                        f"Frame a {story_panel.shot_type.replace('_', ' ')} from a "
                        f"{story_panel.camera_angle.replace('_', ' ')} angle; prioritize "
                        f"{story_panel.action}."
                    ),
                    balloon_placement=(
                        ["upper-right safe area, following right-to-left reading order"]
                        if has_dialogue
                        else []
                    ),
                )
            )
        pages.append(
            PageLayout(
                page_number=story_page.page_number,
                reading_direction="right_to_left",
                layout_strategy=(
                    f"Structured {len(panels)}-panel Japanese manga grid with a dominant "
                    "opening beat and unambiguous right-to-left eye flow."
                ),
                gutter_notes="Consistent safe gutters; no ordinary panels overlap.",
                panels=panels,
            )
        )
    return LayoutOutput(
        design_rationale=(
            "Deterministic production template selected from panel count, narrative order, "
            "and focal beat; geometry is guaranteed to remain inside the page."
        ),
        pages=pages,
    )
