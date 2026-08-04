from __future__ import annotations

from html import escape


DEMO_PANELS = [
    {
        "panel_id": "p1_panel_1",
        "action": "Mai discovers a black feather suspended above her sketchbook.",
        "dialogue": [{"speaker": "Mai", "text": "Chiếc lông này... đang viết tên mình?", "delivery": "whisper"}],
        "shot": "wide",
    },
    {
        "panel_id": "p1_panel_2",
        "action": "The feather draws a doorway while Khoa rushes into the art room.",
        "dialogue": [{"speaker": "Khoa", "text": "Mai, lùi lại!", "delivery": "shout"}],
        "shot": "medium",
    },
    {
        "panel_id": "p1_panel_3",
        "action": "Mai grips the feather and faces the ink doorway.",
        "dialogue": [{"speaker": "Mai", "text": "Nếu nó gọi mình, mình sẽ trả lời.", "delivery": "determined"}],
        "shot": "close_up",
    },
]


def demo_project() -> dict:
    panels = []
    layout_panels = []
    generation_panels = []
    render_panels = []
    boxes = [
        {"x": 0.035, "y": 0.025, "width": 0.93, "height": 0.44},
        {"x": 0.51, "y": 0.495, "width": 0.455, "height": 0.48},
        {"x": 0.035, "y": 0.495, "width": 0.445, "height": 0.48},
    ]
    for index, (panel, box) in enumerate(zip(DEMO_PANELS, boxes, strict=True), start=1):
        panel_id = panel["panel_id"]
        panels.append({
            "panel_number": index,
            "panel_id": panel_id,
            "action": panel["action"],
            "dialogue": panel["dialogue"],
            "setting": "Phòng mỹ thuật cũ của trường",
            "time_of_day": "hoàng hôn",
            "characters": ["Mai"] if index != 2 else ["Mai", "Khoa"],
            "visual_description": panel["action"],
            "shot_type": panel["shot"],
            "camera_angle": "eye_level",
            "mood": ["bí ẩn", "khẩn cấp", "quyết tâm"][index - 1],
            "narration": None,
            "sound_effects": ["SỘT"] if index == 1 else (["RẦM"] if index == 2 else []),
        })
        layout_panels.append({
            "panel_id": panel_id,
            "reading_order": index,
            "box": box,
            "shape": "horizontal" if index == 1 else "rectangle",
            "border": "thick" if index == 1 else "standard",
            "bleed": index == 1,
            "focal_weight": "major" if index == 1 else "normal",
            "composition_notes": panel["action"],
        })
        generation_panels.append({
            "panel_id": panel_id,
            "positive_prompt": (
                "monochrome Japanese manga, Mai, short straight black bob with one silver hairpin, "
                "round dark glasses, sailor school uniform, same face and outfit, " + panel["action"]
            ),
            "negative_prompt": "color, text, speech bubble, inconsistent face, different outfit, extra fingers",
            "character_consistency": [
                "char_mai: short straight black bob, one silver hairpin on left, round dark glasses, sailor uniform"
            ],
            "composition_control": panel["action"],
            "dialogue_overlay": [line["text"] for line in panel["dialogue"]],
            "parameters": {"width": 768, "height": 512 if index == 1 else 896, "steps": 28, "cfg_scale": 5.5, "sampler": "euler_ancestral", "aspect_ratio": "3:2" if index == 1 else "2:3"},
        })
        render_panels.append({
            "panel_id": panel_id,
            "status": "completed",
            "backend": "mock",
            "image_url": f"/demo-art/{panel_id}.svg",
            "seed": 24051996,
            "width": 768,
            "height": 512 if index == 1 else 896,
        })
    return {
        "run_id": "demo-the-ink-door",
        "status": "accept",
        "model": "curated-demo",
        "revision_count": 1,
        "story": {
            "title": "Cánh Cửa Mực",
            "logline": "Một nữ sinh phải bước qua cánh cửa do cây bút lạ vẽ ra để cứu ký ức đang biến mất của mình.",
            "genre": ["mystery", "fantasy"],
            "themes": ["ký ức", "lòng can đảm"],
            "visual_tone": "Manga đen trắng, tương phản mạnh, screentone hoàng hôn.",
            "characters": [
                {"name": "Mai", "role": "Nhân vật chính", "appearance": "Tóc bob đen thẳng, kẹp tóc bạc bên trái, kính tròn tối màu, đồng phục thủy thủ.", "personality": "Tò mò nhưng thận trọng", "motivation": "Giữ lại ký ức về người chị gái"},
                {"name": "Khoa", "role": "Bạn đồng hành", "appearance": "Tóc đen rối, một nốt ruồi dưới mắt phải, áo sơ mi trắng xắn tay.", "personality": "Thực tế, trung thành", "motivation": "Ngăn Mai trả giá cho cây bút"},
            ],
            "outline": [
                {"beat_number": 1, "name": "Vật lạ", "summary": "Mai phát hiện chiếc lông đen tự viết trong phòng mỹ thuật.", "emotional_goal": "Tò mò"},
                {"beat_number": 2, "name": "Cảnh báo", "summary": "Khoa xuất hiện khi nét mực mở thành một cánh cửa.", "emotional_goal": "Căng thẳng"},
                {"beat_number": 3, "name": "Lựa chọn", "summary": "Mai quyết định bước tới thay vì bỏ chạy.", "emotional_goal": "Quyết tâm"},
            ],
            "pages": [{"page_number": 1, "purpose": "Giới thiệu bí ẩn và quyết định của Mai.", "panels": panels, "page_turn_hook": "Một bàn tay giống hệt Mai thò ra từ cánh cửa."}],
        },
        "layout": {"design_rationale": "Panel mở đầu lớn tạo không khí; hai panel dưới tăng tốc nhịp đọc phải sang trái.", "pages": [{"page_number": 1, "layout_strategy": "Một establishing panel và hai reaction panels", "panels": layout_panels}]},
        "generation": {"recommended_checkpoint": "Animagine XL", "global_style_prefix": "monochrome manga, crisp ink, screentone", "panels": generation_panels, "continuity_notes": ["Khóa kẹp tóc, kính và đồng phục của Mai trong mọi panel."]},
        "render": {"backend": "mock", "checkpoint": "curated-demo", "panels": render_panels},
        "critique": {
            "overall_score": 8.8,
            "decision": "accept",
            "summary": "Nhịp đọc rõ, nhận diện nhân vật ổn định và toàn bộ lời thoại đã được tách thành lớp lettering.",
            "panel_critiques": [{"panel_id": p["panel_id"], "score": 8.8, "strengths": ["Nhận diện nhân vật rõ", "Bố cục đúng nhịp"], "issues": [], "correction": None} for p in DEMO_PANELS],
            "regeneration_instructions": [],
            "lora_training": {"eligible": False, "reason": "Dữ liệu minh họa, không dùng huấn luyện", "quality_score": 8.8, "caption_tags": ["manga", "school", "mystery"]},
        },
    }


def demo_panel_svg(panel_id: str) -> str:
    index = next((i for i, panel in enumerate(DEMO_PANELS) if panel["panel_id"] == panel_id), 0)
    backgrounds = ["#e7e2d8", "#c9c3b8", "#ddd8ce"]
    door = '<path d="M520 80 L690 42 L690 760 L520 710 Z" fill="#151515"/><path d="M545 120 L666 92 L666 708 L545 670 Z" fill="#f4f0e7" stroke="#111" stroke-width="8"/>' if index else ''
    khoa = '<circle cx="590" cy="310" r="64" fill="#eee" stroke="#111" stroke-width="8"/><path d="M525 300 Q590 190 655 300" fill="#111"/><path d="M535 380 L650 380 L704 730 L490 730 Z" fill="#fafafa" stroke="#111" stroke-width="8"/>' if index == 1 else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 896">
<rect width="768" height="896" fill="{backgrounds[index]}"/>
<defs><pattern id="tone" width="10" height="10" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.4" fill="#777"/></pattern></defs>
<path d="M0 620 Q210 520 768 590 L768 896 L0 896 Z" fill="url(#tone)"/>{door}{khoa}
<circle cx="{300 if index != 1 else 235}" cy="330" r="105" fill="#f5f2ea" stroke="#111" stroke-width="10"/>
<path d="M190 328 Q225 150 342 215 Q412 270 392 390 Q345 260 203 365 Z" fill="#111"/>
<path d="M193 302 Q265 230 380 302" fill="none" stroke="#111" stroke-width="28"/>
<circle cx="235" cy="334" r="34" fill="none" stroke="#111" stroke-width="8"/><circle cx="327" cy="334" r="34" fill="none" stroke="#111" stroke-width="8"/><path d="M269 334 L293 334" stroke="#111" stroke-width="7"/>
<circle cx="235" cy="334" r="5"/><circle cx="327" cy="334" r="5"/><path d="M265 390 Q285 {405 if index == 2 else 385} 310 390" fill="none" stroke="#111" stroke-width="6"/>
<rect x="196" y="206" width="34" height="9" rx="4" fill="#ddd" transform="rotate(-18 196 206)"/>
<path d="M155 455 Q285 405 410 455 L480 896 L75 896 Z" fill="#f8f8f5" stroke="#111" stroke-width="10"/><path d="M200 455 L285 590 L367 455" fill="none" stroke="#111" stroke-width="11"/>
<path d="M{405 if index == 2 else 430} 610 Q520 510 570 350" fill="none" stroke="#111" stroke-width="22" stroke-linecap="round"/>
<path d="M555 360 Q600 190 645 90 Q610 250 575 370 Z" fill="#111"/>
<g opacity=".3"><path d="M20 80 L180 20 M10 160 L260 20 M600 880 L760 720" stroke="#111" stroke-width="5"/></g>
<text x="32" y="850" font-family="Arial" font-size="24" font-weight="700" fill="#555">{escape(panel_id.upper())} · CONSISTENT CHARACTER STUDY</text>
</svg>'''
