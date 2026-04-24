from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image
import httpx
import numpy as np

SYSTEM_PROMPT = """You are a calm, wonder-filled nature-documentary narrator in the
tradition of BBC
wildlife programmes. You are watching a game on screen and narrating it as if it
were a rare scene from the natural world. Observe the creature (or vessel, vehicle,
or figure) on screen with the same reverence you would give a pangolin or a lyrebird.

Rules:
- 1 to 2 sentences, present tense, British phrasing.
- Hushed, measured, slightly awed. Short clauses. No exclamation marks.
- Use biology / ecology metaphors where natural: instinct, territory, courtship,
  peril, lineage, survival, the edge of exhaustion.
- Do not name the game. Do not mention pixels, screens, scores, or controllers.
- Do not name real people. You are a narrator, not the narrator.
- If nothing has changed, say so gently (e.g., \"A pause. The creature gathers
  itself.\")."""


@dataclass(slots=True)
class NarrationContext:
    """Context fields sent alongside a frame for continuity-aware narration."""

    env_human_name: str
    previous_narration: str = ""
    event_summary: str = ""


class VLMNarrator:
    """OpenAI-compatible multimodal client for frame-to-text narration."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        image_detail: str = "low",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._image_detail = image_detail
        self._timeout_seconds = timeout_seconds

    async def narrate_frame(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Generate one short narration from an RGB frame and context."""

        image_payload = self._encode_image_payload(frame)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._build_user_message(context),
                        },
                        image_payload,
                    ],
                },
            ],
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "top_p": self._top_p,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        content = body["choices"][0]["message"]["content"]
        normalized = self._normalize_message_content(content)
        return normalized or "A pause. The creature gathers itself."

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Synchronous wrapper used by Stage 4 single-loop integration."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.narrate_frame(frame=frame, context=context))

        raise RuntimeError(
            "narrate_frame_sync cannot be used from a running event loop; "
            "await narrate_frame instead."
        )

    async def wait_until_ready(
        self,
        *,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 1.0,
    ) -> bool:
        """Poll /models until the VLM endpoint responds successfully."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        deadline = asyncio.get_running_loop().time() + timeout_seconds

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    response = await client.get(f"{self._base_url}/models")
                    if response.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass

                await asyncio.sleep(poll_interval_seconds)

        return False

    def wait_until_ready_sync(
        self,
        *,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 1.0,
    ) -> bool:
        """Synchronous wrapper for endpoint readiness polling."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.wait_until_ready(
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                )
            )

        raise RuntimeError(
            "wait_until_ready_sync cannot be used from a running event loop; "
            "await wait_until_ready instead."
        )

    @staticmethod
    def _build_user_message(context: NarrationContext) -> str:
        return (
            "Context:\n"
            f"- Scene: {context.env_human_name}\n"
            f'- Last narration (for continuity): "{context.previous_narration}"\n'
            f"- Recent events: {context.event_summary}\n\n"
            "Narrate this moment."
        )

    @staticmethod
    def _normalize_message_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return " ".join(text.strip() for text in texts if text).strip()

        return ""

    def _encode_image_payload(self, frame: np.ndarray) -> dict[str, Any]:
        if frame.ndim != 3 or frame.shape[2] not in {3, 4}:
            raise ValueError(
                f"Expected RGB/RGBA frame with shape (H, W, 3|4), got {frame.shape}"
            )

        image_array = frame[:, :, :3]
        if image_array.dtype != np.uint8:
            image_array = np.clip(image_array, 0, 255).astype(np.uint8)

        image = Image.fromarray(image_array)
        if self._image_detail == "low":
            image = self._downscale_long_edge(image, max_long_edge=384)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded}",
                "detail": self._image_detail,
            },
        }

    @staticmethod
    def _downscale_long_edge(image: Image.Image, max_long_edge: int) -> Image.Image:
        width, height = image.size
        long_edge = max(width, height)
        if long_edge <= max_long_edge:
            return image

        scale = max_long_edge / float(long_edge)
        resized = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        return image.resize(resized, Image.Resampling.BILINEAR)
