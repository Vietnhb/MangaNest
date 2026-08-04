import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from ollama import AsyncClient as OllamaAsyncClient
from PIL import Image

from app.prompts.critique import CRITIQUE_SYSTEM_PROMPT
from app.schemas.critique import CritiqueOutput, LoRATrainingCandidate, PanelCritique


class VisionCritiqueAgent:
    """Critique rendered panels through the configured vision provider."""

    def __init__(self, model: BaseChatModel) -> None:
        self.model = model
        self.structured_model = model.with_structured_output(
            CritiqueOutput,
            method="json_schema",
        )

    @staticmethod
    def _image_bytes(path: str, max_size: int = 768) -> bytes:
        with Image.open(Path(path)) as source:
            image = source.convert("RGB")
            image.thumbnail((max_size, max_size))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=82, optimize=True)
        return buffer.getvalue()

    @classmethod
    def _image_data_url(cls, path: str, max_size: int = 768) -> str:
        encoded = base64.b64encode(cls._image_bytes(path, max_size)).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    async def ainvoke(self, payload: dict[str, Any], image_paths: list[str]) -> CritiqueOutput:
        if self.model.__class__.__name__ == "ChatOllama":
            return await self._ainvoke_local_json(payload, image_paths)
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
        render_panels = payload.get("input", {}).get("render", {}).get("panels", [])
        panel_ids = [
            panel.get("panel_id", f"image_{index + 1}")
            for index, panel in enumerate(render_panels)
            if panel.get("status") == "completed" and panel.get("image_path")
        ]
        for index, path in enumerate(image_paths):
            panel_id = panel_ids[index] if index < len(panel_ids) else f"image_{index + 1}"
            content.extend([
                {
                    "type": "text",
                    "text": f"The next attached image is exactly panel_id={panel_id}. Review only what is visible in it.",
                },
                {"type": "image_url", "image_url": self._image_data_url(path)},
            ])
        result = await self.structured_model.ainvoke(
            [
                SystemMessage(content=CRITIQUE_SYSTEM_PROMPT),
                HumanMessage(content=content),
            ]
        )
        if isinstance(result, CritiqueOutput):
            return result
        return CritiqueOutput.model_validate(result)

    async def _ainvoke_local_json(
        self, payload: dict[str, Any], image_paths: list[str]
    ) -> CritiqueOutput:
        """Use a compact JSON contract that small local VLMs follow reliably."""
        story_panels = {
            panel["panel_id"]: panel
            for page in payload.get("input", {}).get("story", {}).get("pages", [])
            for panel in page.get("panels", [])
        }
        render_panels = [
            panel for panel in payload.get("input", {}).get("render", {}).get("panels", [])
            if panel.get("status") == "completed" and panel.get("image_path")
        ]
        requirements = []
        for panel in render_panels:
            story = story_panels.get(panel["panel_id"], {})
            requirements.append({
                "panel_id": panel["panel_id"],
                "setting": story.get("setting", ""),
                "action": story.get("action", ""),
                "visual_description": story.get("visual_description", ""),
                "shot_type": story.get("shot_type", ""),
            })
        contract = {
            "score": "number 0-10", "strengths": ["visible strengths"],
            "issues": ["visible or fidelity failures"], "correction": "specific fix or null",
        }
        critiques: list[PanelCritique] = []
        client = OllamaAsyncClient(host=getattr(self.model, "base_url", None))
        for requirement, path in zip(requirements, image_paths, strict=True):
            prompt = (
                        "Review this exact manga panel against the requested scene. Verify every central subject, "
                        "action and shot requirement. If a central subject/action is missing, score MUST be <=5.5. "
                        "Do not reward generic prettiness over story fidelity and do not invent invisible defects. "
                        "Dialogue, captions, speech bubbles and sound effects are added in post-processing; never "
                        "penalize the artwork for omitting text, bubbles, lettering, or an open speaking mouth. "
                f"Panel requirement: {json.dumps(requirement, ensure_ascii=False)}. "
                f"Return JSON only with exactly this shape: {json.dumps(contract)}"
            )
            response = await client.chat(
                model=getattr(self.model, "model"),
                messages=[{
                    "role": "user", "content": prompt,
                    "images": [self._image_bytes(path, max_size=448)],
                }],
                format="json", think=False,
                options={"num_predict": 512, "temperature": 0},
            )
            raw = response.message.content or response.message.thinking or ""
            decoded = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            issues = [
                issue for issue in decoded.get("issues", [])
                if not any(term in issue.casefold() for term in (
                    "speech bubble", "dialogue bubble", "missing text", "no text",
                    "mouth open", "open speaking mouth",
                ))
            ]
            correction = decoded.get("correction")
            if correction and any(term in correction.casefold() for term in ("speech bubble", "dialogue bubble")):
                correction = "; ".join(
                    part.strip() for part in correction.split(";")
                    if "bubble" not in part.casefold()
                ) or None
            critiques.append(PanelCritique(
                panel_id=requirement["panel_id"],
                score=decoded["score"], strengths=decoded.get("strengths", []),
                issues=issues, correction=correction,
            ))
        overall = round(sum(item.score for item in critiques) / len(critiques), 2)
        return CritiqueOutput(
            overall_score=overall,
            decision="accept" if overall >= 7.5 and all(item.score >= 7 for item in critiques) else "regenerate",
            summary=f"Fresh local visual review completed for {len(critiques)} rendered panels; lowest panel score is {min(item.score for item in critiques):.1f}.",
            panel_critiques=critiques,
            regeneration_instructions=[
                f"{item.panel_id}: {item.correction}"
                for item in critiques if item.score < 7 and item.correction
            ],
            lora_training=LoRATrainingCandidate(
                eligible=overall >= 8 and all(item.score >= 7.5 for item in critiques),
                reason="Eligible only when every visually reviewed panel clears the dataset threshold.",
                caption_tags=["manga", "black and white", "reviewed"],
                quality_score=overall,
                required_metadata=["panel_id", "character_identity", "story_action"],
            ),
        )
