import asyncio
import base64
import hashlib
import io
import json
import logging
import re
import textwrap
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.core.config import Settings
from app.schemas.generation import GenerationOutput, PanelGenerationPrompt
from app.schemas.render import PanelRender, RenderOutput

RenderMode = Literal["prompt_only", "mock", "comfyui"]
logger = logging.getLogger(__name__)

_CHROMATIC_COLOR = re.compile(
    r"\b(red|blue|green|yellow|orange|purple|pink|cyan|magenta|teal|golden)\b",
    flags=re.IGNORECASE,
)

_SUBJECT_TAG = re.compile(r"^(?:\d+girls?|\d+boys?|\d+others?|solo|multiple (?:girls|boys|people))$", re.IGNORECASE)


def _monochrome_description(value: str) -> str:
    """Preserve canonical color identity as a readable grayscale tone."""
    return _CHROMATIC_COLOR.sub("distinctive dark-toned", value)


def _prompt_tags(*sections: str, limit: int) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for section in sections:
        for raw in re.split(r"[,;\n]+", section):
            tag = re.sub(r"\s+", " ", raw).strip(" .")
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
            if len(tags) >= limit:
                return tags
    return tags


def _compile_animagine_positive(panel: PanelGenerationPrompt, generation: GenerationOutput) -> str:
    raw_tags = _prompt_tags(_monochrome_description(panel.positive_prompt), limit=48)
    subjects = [tag for tag in raw_tags if _SUBJECT_TAG.fullmatch(tag)]
    details = [tag for tag in raw_tags if tag not in subjects]
    identity = ", ".join(_monochrome_description(item) for item in panel.character_consistency)
    return ", ".join(_prompt_tags(
        ", ".join(subjects), identity, ", ".join(details), panel.composition_control,
        _monochrome_description(generation.global_style_prefix),
        "single uninterrupted illustration, one scene, no frames, no borders, monochrome, grayscale, "
        "black and white, crisp inked lineart, screentone, high contrast",
        "safe, masterpiece, high score, great score, absurdres", limit=64,
    ))


def _compile_animagine_negative(panel: PanelGenerationPrompt, generation: GenerationOutput) -> str:
    return ", ".join(_prompt_tags(
        "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, "
        "worst quality, low quality, low score, bad score, average score, signature, watermark, username, blurry",
        "color, colorful, multiple panels, manga page, comic page, comic strip, panel grid, collage, split screen, "
        "contact sheet, frame, panel border, speech bubble, lettering",
        generation.global_negative_prefix, panel.negative_prompt, limit=64,
    ))


def _bounded_dimensions(
    width: int,
    height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    aspect_ratio = width / height
    if aspect_ratio >= 1.25:
        width, height = 1216, 832
    elif aspect_ratio <= 0.8:
        width, height = 832, 1216
    else:
        width, height = 1024, 1024
    scale = min(max_width / width, max_height / height, 1.0)
    bounded_width = max(256, int(width * scale) // 64 * 64)
    bounded_height = max(256, int(height * scale) // 64 * 64)
    return bounded_width, bounded_height


def _normalize_manga_art(path: Path) -> None:
    with Image.open(path) as source:
        normalized = ImageOps.grayscale(source).filter(
            ImageFilter.UnsharpMask(radius=0.45, percent=25, threshold=4)
        )
        normalized.save(path, format="PNG", optimize=True)


def _technical_candidate_score(path: Path) -> float:
    with Image.open(path) as source:
        image = ImageOps.grayscale(source).resize((256, 256), Image.Resampling.BILINEAR)
        histogram = image.histogram()
        pixels = image.width * image.height
        clipped = (sum(histogram[:4]) + sum(histogram[-4:])) / pixels
        entropy = image.entropy()
        edges = image.filter(ImageFilter.FIND_EDGES)
        edge_energy = sum(i * count for i, count in enumerate(edges.histogram())) / (pixels * 255)
    return entropy + edge_energy * 2.0 - clipped * 3.0


def _candidate_is_flat(path: Path) -> bool:
    with Image.open(path) as source:
        gray = ImageOps.grayscale(source).resize((256, 256), Image.Resampling.BILINEAR)
        extrema = gray.getextrema()
        return gray.entropy() < 3.0 or (extrema[1] - extrema[0]) < 24


class RenderingService:
    """Dispatch panel prompts to prompt-only, mock, or local ComfyUI rendering."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.output_dir = Path(settings.render_output_dir)

    async def render(
        self,
        generation: GenerationOutput,
        revision_count: int,
        mode: RenderMode,
        identity_references: dict[str, str] | None = None,
    ) -> RenderOutput:
        if mode == "prompt_only":
            return self._prompt_only(generation)
        if mode == "mock":
            return await asyncio.to_thread(
                self._render_mock, generation, revision_count
            )
        return await self._render_comfyui(generation, revision_count, identity_references)

    def _prompt_only(self, generation: GenerationOutput) -> RenderOutput:
        return RenderOutput(
            backend="prompt_only",
            checkpoint=generation.recommended_checkpoint,
            workflow_version="prompt-only-v1",
            panels=[
                PanelRender(
                    panel_id=panel.panel_id,
                    status="prompt_only",
                    backend="prompt_only",
                    width=panel.parameters.width,
                    height=panel.parameters.height,
                )
                for panel in generation.panels
            ],
        )

    def _render_mock(
        self,
        generation: GenerationOutput,
        revision_count: int,
    ) -> RenderOutput:
        mock_dir = self.output_dir / "mock"
        mock_dir.mkdir(parents=True, exist_ok=True)
        panels: list[PanelRender] = []
        for index, panel in enumerate(generation.panels, start=1):
            width, height = _bounded_dimensions(
                panel.parameters.width,
                panel.parameters.height,
                self.settings.render_max_width,
                self.settings.render_max_height,
            )
            seed = abs(hash((panel.panel_id, revision_count))) % 2_147_483_647
            image = Image.new("L", (width, height), color=245)
            draw = ImageDraw.Draw(image)
            draw.rectangle((12, 12, width - 13, height - 13), outline=12, width=5)
            draw.rectangle((28, 28, width - 29, 112), fill=25)
            draw.text((44, 50), f"MANGAFORGE / {panel.panel_id}", fill=255)
            body = "\n".join(textwrap.wrap(panel.positive_prompt, width=48)[:18])
            draw.multiline_text((44, 145), body, fill=20, spacing=8)
            draw.text(
                (44, height - 64),
                f"MOCK RENDER  |  revision {revision_count}  |  seed {seed}",
                fill=20,
                font=ImageFont.load_default(),
            )
            filename = f"{panel.panel_id}_r{revision_count}_{index}.png"
            path = mock_dir / filename
            image.save(path)
            panels.append(
                PanelRender(
                    panel_id=panel.panel_id,
                    status="completed",
                    backend="mock",
                    image_path=str(path.resolve()),
                    image_url=f"/outputs/mock/{filename}",
                    seed=seed,
                    width=width,
                    height=height,
                )
            )
        return RenderOutput(
            backend="mock",
            checkpoint="mock-renderer",
            workflow_version="mock-v1",
            panels=panels,
        )

    async def _render_comfyui(
        self,
        generation: GenerationOutput,
        revision_count: int,
        identity_references: dict[str, str] | None = None,
    ) -> RenderOutput:
        if self.settings.vision_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=15) as ollama:
                    await ollama.post(
                        f"{self.settings.ollama_base_url}/api/generate",
                        json={"model": self.settings.ollama_vision_model, "keep_alive": 0},
                    )
            except Exception:
                logger.warning("Could not release the local vision model before rendering", exc_info=True)
        async with httpx.AsyncClient(
            base_url=self.settings.comfyui_base_url,
            timeout=self.settings.comfyui_timeout_seconds,
        ) as client:
            health = await client.get("/system_stats")
            health.raise_for_status()
            rendered: list[PanelRender] = []
            references = {
                key: value for key, value in (identity_references or {}).items()
                if Path(value).exists()
            }
            uploaded_references: dict[str, str] = {}
            for panel in generation.panels:
                reference_image = None
                identity_profile = self._identity_conditioning_profile(panel)
                reference_key = self._identity_reference_key(panel)
                if self.settings.comfyui_ipadapter_enabled and reference_key and identity_profile:
                    if reference_key not in references:
                        reference = await self._render_identity_reference(
                            client, panel, generation, revision_count, reference_key
                        )
                        if reference.image_path:
                            references[reference_key] = reference.image_path
                    reference_path = references.get(reference_key)
                    if reference_path:
                        if reference_key not in uploaded_references:
                            uploaded_references[reference_key] = await self._upload_reference(
                                client, Path(reference_path), reference_key
                            )
                        reference_image = uploaded_references[reference_key]
                rendered.append(
                    await self._render_comfyui_panel(
                        client, panel, generation, revision_count, reference_image,
                        identity_profile[0] if identity_profile else None,
                        identity_profile[1] if identity_profile else None,
                    )
                )
        return RenderOutput(
            backend="comfyui",
            checkpoint=self.settings.comfyui_checkpoint,
            workflow_version="sdxl-ipadapter-native-candidates-v7" if self.settings.comfyui_ipadapter_enabled else "sdxl-native-candidates-v3",
            panels=rendered,
            identity_references=references,
        )

    @staticmethod
    def _identity_reference_key(panel: PanelGenerationPrompt) -> str | None:
        if not panel.character_consistency:
            return None
        identity = panel.character_consistency[0].strip().casefold()
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]

    def _identity_conditioning_profile(
        self, panel: PanelGenerationPrompt
    ) -> tuple[float, float] | None:
        """Balance identity locking against scene and multi-character composition."""
        if panel.identity_mode == "off" or not panel.character_consistency:
            return None
        scene = f"{panel.positive_prompt} {panel.composition_control}".casefold()
        multi_subject = any(token in scene for token in (
            "reflected adult", "two distinct faces", "1girl and one", "multiple characters",
            "two people", "2girls", "1girl, 1boy",
        ))
        if panel.identity_mode == "auto" and multi_subject:
            return None
        if panel.identity_strength is not None:
            return panel.identity_strength, self.settings.comfyui_ipadapter_end_at
        if "wide" in scene or "establishing" in scene:
            return min(self.settings.comfyui_ipadapter_weight, 0.20), 0.50
        if "close-up" in scene or "close up" in scene or "portrait" in scene:
            return min(self.settings.comfyui_ipadapter_weight, 0.38), 0.65
        return min(self.settings.comfyui_ipadapter_weight, 0.28), 0.58

    async def _render_identity_reference(
        self,
        client: httpx.AsyncClient,
        panel: PanelGenerationPrompt,
        generation: GenerationOutput,
        revision_count: int,
        reference_key: str,
    ) -> PanelRender:
        anchor = _monochrome_description(panel.character_consistency[0])
        reference_panel = panel.model_copy(update={
            "panel_id": f"identity_{reference_key}",
            "positive_prompt": (
                f"solo character, {anchor}, centered upper-body character reference portrait, "
                "front three-quarter view, neutral expression, face fully visible, hairstyle and outfit fully visible, "
                "plain light gray studio background, clean professional manga character sheet, precise facial features"
            ),
            "negative_prompt": (
                "multiple people, duplicate person, profile only, face hidden, cropped head, cropped hair, "
                "action pose, complex background, text, labels, character turnaround grid"
            ),
            "character_consistency": [],
            "composition_control": "centered upper-body identity reference",
            "dialogue_overlay": [],
            "parameters": panel.parameters.model_copy(update={
                "aspect_ratio": "1:1", "width": 640, "height": 640,
            }),
        })
        return await self._render_comfyui_panel(
            client, reference_panel, generation, revision_count, None
        )

    @staticmethod
    async def _upload_reference(
        client: httpx.AsyncClient, path: Path, reference_key: str
    ) -> str:
        with path.open("rb") as source:
            response = await client.post(
                "/upload/image",
                files={"image": (f"mangaforge_ref_{reference_key}.png", source, "image/png")},
                data={"type": "input", "overwrite": "true"},
            )
        response.raise_for_status()
        payload = response.json()
        subfolder = payload.get("subfolder", "")
        return f"{subfolder}/{payload['name']}".lstrip("/")

    async def _render_comfyui_panel(
        self,
        client: httpx.AsyncClient,
        panel: PanelGenerationPrompt,
        generation: GenerationOutput,
        revision_count: int,
        reference_image: str | None = None,
        reference_strength: float | None = None,
        reference_end_at: float | None = None,
        quality_retry: int = 0,
    ) -> PanelRender:
        width, height = _bounded_dimensions(
            panel.parameters.width,
            panel.parameters.height,
            self.settings.render_max_width,
            self.settings.render_max_height,
        )
        identity_key = (
            panel.character_consistency[0]
            if panel.character_consistency
            else panel.panel_id
        )
        seed_material = (
            f"{self.settings.comfyui_checkpoint}|{identity_key}|{panel.panel_id}|variation:{revision_count}|quality-retry:{quality_retry}".encode("utf-8")
        )
        seed = (
            int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
            % 2_147_483_647
        )
        workflow = self._workflow(
            panel, generation, seed, width, height, revision_count, reference_image,
            reference_strength, reference_end_at,
        )
        response = await client.post("/prompt", json={"prompt": workflow})
        response.raise_for_status()
        payload = response.json()
        prompt_id = payload["prompt_id"]
        deadline = asyncio.get_running_loop().time() + self.settings.comfyui_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            history_response = await client.get(f"/history/{prompt_id}")
            history_response.raise_for_status()
            history = history_response.json()
            if prompt_id in history:
                output = history[prompt_id].get("outputs", {}).get("9", {})
                images = output.get("images", [])
                if images:
                    candidates: list[tuple[Path, Path]] = []
                    for item in images:
                        relative_path = Path(item.get("subfolder", "")) / item["filename"]
                        candidate_path = self.output_dir / relative_path
                        await asyncio.to_thread(_normalize_manga_art, candidate_path)
                        candidates.append((relative_path, candidate_path))
                    usable = [item for item in candidates if not _candidate_is_flat(item[1])]
                    if not usable:
                        if quality_retry < 1:
                            logger.warning("All candidates for %s were flat; retrying with new noise", panel.panel_id)
                            return await self._render_comfyui_panel(
                                client, panel, generation, revision_count, reference_image,
                                reference_strength, reference_end_at, quality_retry + 1,
                            )
                        raise RuntimeError(f"ComfyUI produced only flat candidates for {panel.panel_id}")
                    selected = await self._select_candidate(panel, usable)
                    relative, path = usable[selected]
                    return PanelRender(
                        panel_id=panel.panel_id,
                        status="completed",
                        backend="comfyui",
                        image_path=str(path.resolve()),
                        image_url=f"/outputs/{relative.as_posix()}",
                        prompt_id=prompt_id,
                        seed=seed,
                        width=width,
                        height=height,
                    )
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI failed prompt {prompt_id}: {status}")
            await asyncio.sleep(1)
        raise TimeoutError(f"ComfyUI timed out for panel {panel.panel_id}")

    async def _select_candidate(
        self,
        panel: PanelGenerationPrompt,
        candidates: list[tuple[Path, Path]],
    ) -> int:
        if len(candidates) == 1:
            return 0
        fallback = max(range(len(candidates)), key=lambda i: _technical_candidate_score(candidates[i][1]))
        if not self.settings.comfyui_candidate_selection or self.settings.vision_provider != "ollama":
            return fallback
        try:
            encoded_images: list[str] = []
            for _, path in candidates:
                with Image.open(path) as source:
                    preview = source.convert("RGB")
                    preview.thumbnail((512, 512))
                    buffer = io.BytesIO()
                    preview.save(buffer, format="JPEG", quality=84)
                    encoded_images.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
            requirement = {
                "scene": panel.positive_prompt,
                "composition": panel.composition_control,
                "identity": panel.character_consistency,
            }
            async with httpx.AsyncClient(
                base_url=self.settings.ollama_base_url,
                timeout=self.settings.ollama_timeout_seconds,
            ) as vision_client:
                response = await vision_client.post("/api/chat", json={
                    "model": self.settings.ollama_vision_model,
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {"temperature": 0, "num_predict": 512},
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Compare candidate images 0 through {len(encoded_images) - 1}. Select the image that "
                            "best contains every requested subject and action with correct camera framing. Reject "
                            "missing characters and wrong objects before judging beauty. "
                            f"Requirement: {json.dumps(requirement, ensure_ascii=False)}. "
                            'Return JSON only: {"candidate_index": integer, "reason": "brief"}.'
                        ),
                        "images": encoded_images,
                    }],
                })
            response.raise_for_status()
            message = response.json()["message"]
            raw = (message.get("content") or message.get("thinking") or "").strip()
            raw = raw.removeprefix("```json").removesuffix("```").strip()
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r"\{.*?\}", raw, flags=re.DOTALL)
                if match is None:
                    raise
                decoded = json.loads(match.group(0))
            selected = int(decoded["candidate_index"])
            return selected if 0 <= selected < len(candidates) else fallback
        except Exception:
            logger.warning("Candidate semantic selection failed; using technical ranking", exc_info=True)
            return fallback

    def _workflow(
        self,
        panel: PanelGenerationPrompt,
        generation: GenerationOutput,
        seed: int,
        width: int,
        height: int,
        revision_count: int,
        reference_image: str | None = None,
        reference_strength: float | None = None,
        reference_end_at: float | None = None,
    ) -> dict:
        positive = _compile_animagine_positive(panel, generation)
        negative = _compile_animagine_negative(panel, generation)
        sampler_model: list[int | str] = ["1", 0]
        workflow: dict[str, dict] = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": self.settings.comfyui_checkpoint},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": positive, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": self.settings.comfyui_candidates},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": min(panel.parameters.steps, self.settings.comfyui_steps),
                    "cfg": self.settings.comfyui_cfg_scale,
                    "sampler_name": self.settings.comfyui_sampler,
                    "scheduler": self.settings.comfyui_scheduler,
                    "denoise": 1,
                    "model": sampler_model,
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"mangaforge/{panel.panel_id}_r{revision_count}",
                    "images": ["8", 0],
                },
            },
        }
        if reference_image:
            workflow.update({
                "10": {
                    "class_type": "LoadImage",
                    "inputs": {"image": reference_image},
                },
                "11": {
                    "class_type": "IPAdapterUnifiedLoader",
                    "inputs": {"model": ["1", 0], "preset": "PLUS (high strength)"},
                },
                "12": {
                    "class_type": "IPAdapterAdvanced",
                    "inputs": {
                        "model": ["11", 0], "ipadapter": ["11", 1], "image": ["10", 0],
                        "weight": reference_strength or self.settings.comfyui_ipadapter_weight,
                        "weight_type": "linear", "combine_embeds": "average",
                        "start_at": 0.0, "end_at": reference_end_at or self.settings.comfyui_ipadapter_end_at,
                        "embeds_scaling": "K+V w/ C penalty",
                    },
                },
            })
            workflow["5"]["inputs"]["model"] = ["12", 0]
        return workflow


def create_renderer(settings: Settings) -> RenderingService:
    return RenderingService(settings)
