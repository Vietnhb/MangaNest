import json
from pathlib import Path

import httpx


payload = {
    "idea": (
        "Một nữ sinh tên Aki phát hiện cây bút ma thuật có thể thay đổi ngày mai, "
        "nhưng mỗi nét vẽ khiến một ký ức của cô biến mất."
    ),
    "target_pages": 1,
    "genre": ["fantasy", "mystery"],
    "audience": "teen",
    "manga_style": "cinematic black-and-white Japanese manga",
    "max_revisions": 0,
    "render_mode": "mock",
}

with httpx.Client(timeout=1200) as client:
    response = client.post("http://127.0.0.1:8000/generate-manga", json=payload)
    response.raise_for_status()

output = Path("E:/MangaForgeAI/outputs/demo-result.json")
output.write_text(
    json.dumps(response.json(), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(output.resolve())
