"""Vision-language narration client used by runtime and wrapper pipelines.

The module encapsulates prompt construction, image payload encoding, and OpenAI-
compatible HTTP calls so orchestration code can request narration with a small,
stable interface.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image
import httpx
import numpy as np

from docugym.narration_defaults import DEFAULT_NARRATION_TEXT
from docugym.prompts import DEFAULT_SYSTEM_PROMPT, get_system_prompt

SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


@dataclass(slots=True)
class NarrationContext:
    """Continuity fields supplied with each narration request.

    Attributes:
        env_human_name: Human-readable scene name used in the prompt context.
        previous_narration: Most recent narration text for continuity.
        event_summary: Compact summary of recent events/triggers.
    """

    env_human_name: str
    previous_narration: str = ""
    event_summary: str = ""


class VLMNarrator:
    """OpenAI-compatible multimodal narrator for RGB frame inputs.

    Instances are reusable across many narration requests and keep one async client
    per event loop to benefit from HTTP connection pooling in long sessions.

    Example:
        narrator = VLMNarrator(
            base_url="http://localhost:8000/v1",
            model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
            max_tokens=80,
            temperature=0.8,
            top_p=0.9,
        )
        text = await narrator.narrate_frame(frame=frame, context=context)
    """

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
        readiness_timeout_seconds: float = 5.0,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize narrator transport and sampling parameters.

        Args:
            base_url: OpenAI-compatible HTTP endpoint base URL.
            model: Model identifier sent to ``/chat/completions``.
            max_tokens: Completion token cap per narration request.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.
            image_detail: Image detail hint passed to the multimodal endpoint.
            timeout_seconds: Request timeout for narration calls.
            readiness_timeout_seconds: Timeout for readiness polling requests.
            system_prompt: Optional per-instance system prompt. When omitted,
                the process-wide prompt from ``docugym.prompts`` is used.

        Raises:
            ValueError: If ``base_url`` is not an absolute http(s) URL or
                ``system_prompt`` is blank.
        """

        parsed_base_url = httpx.URL(base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.host:
            raise ValueError("base_url must be an absolute http(s) URL")

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._image_detail = image_detail
        self._timeout_seconds = timeout_seconds
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._system_prompt = self._normalize_system_prompt(system_prompt)
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    async def narrate_frame(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Generate one narration string from a frame and continuity context.

        The frame is encoded off the event loop, then submitted to an OpenAI-style
        ``/chat/completions`` endpoint with both system and contextual user prompt
        content.

        Args:
            frame: RGB/RGBA frame array with shape ``(H, W, C)``.
            context: Prompt continuity payload.

        Returns:
            Narration text, or fallback narration when response content is empty.

        Raises:
            ValueError: If frame shape/channels are invalid during encoding.
            httpx.HTTPError: If the backend request fails.
        """

        image_payload = await asyncio.to_thread(self._encode_image_payload, frame)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._effective_system_prompt()},
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

        client = await self._get_client()
        body = await self._post_chat_completion(client, payload)

        content = body["choices"][0]["message"]["content"]
        normalized = self._normalize_message_content(content)
        return normalized or DEFAULT_NARRATION_TEXT

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Synchronous narration API for non-async integration points.

        This method intentionally creates a short-lived async client per call to
        avoid cross-loop reuse hazards in synchronous code paths.

        Args:
            frame: RGB/RGBA frame encoded and sent to the VLM endpoint.
            context: Prompt context carrying scene, event, and continuity details.

        Returns:
            Narration text, or fallback narration when response content is empty.

        Raises:
            RuntimeError: If called from a running event loop.
        """

        async def _run_once() -> str:
            image_payload = await asyncio.to_thread(self._encode_image_payload, frame)
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": self._effective_system_prompt()},
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
                body = await self._post_chat_completion(client, payload)
            content = body["choices"][0]["message"]["content"]
            normalized = self._normalize_message_content(content)
            return normalized or DEFAULT_NARRATION_TEXT

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_run_once())

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
        """Poll ``/models`` until the VLM endpoint responds with HTTP 200.

        This is intended for startup gating in CLI flows where a sidecar model
        server may need warm-up time before first narration requests.

        Args:
            timeout_seconds: Maximum polling duration.
            poll_interval_seconds: Delay between probes.

        Returns:
            ``True`` when endpoint readiness is confirmed; otherwise ``False``.

        Raises:
            ValueError: If ``timeout_seconds`` is non-positive.
        """

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        deadline = asyncio.get_running_loop().time() + timeout_seconds

        async with httpx.AsyncClient(timeout=self._readiness_timeout_seconds) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    response = await client.get(f"{self._base_url}/models")
                    if response.status_code == 200:
                        return True
                except httpx.RequestError:
                    pass

                await asyncio.sleep(poll_interval_seconds)

        return False

    async def aclose(self) -> None:
        """Close the persistent async HTTP client if it exists.

        Call this during application shutdown to release pooled connections
        associated with the active event loop.
        """

        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._client_loop = None

    def wait_until_ready_sync(
        self,
        *,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 1.0,
    ) -> bool:
        """Synchronous wrapper around :meth:`wait_until_ready`.

        Args:
            timeout_seconds: Maximum polling duration.
            poll_interval_seconds: Delay between readiness probes.

        Raises:
            RuntimeError: If called while an event loop is running.

        Returns:
            ``True`` when endpoint readiness is confirmed; otherwise ``False``.
        """

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
    def _normalize_system_prompt(system_prompt: str | None) -> str | None:
        if system_prompt is None:
            return None

        normalized = system_prompt.strip()
        if not normalized:
            raise ValueError("system_prompt must not be empty")
        return normalized

    def _effective_system_prompt(self) -> str:
        return self._system_prompt or get_system_prompt()

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

    async def _get_client(self) -> httpx.AsyncClient:
        current_loop = asyncio.get_running_loop()
        if self._client is not None and self._client_loop is current_loop:
            is_closed = getattr(self._client, "is_closed", False)
            if not is_closed:
                return self._client

        if self._client is not None:
            await self._client.aclose()

        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        self._client_loop = current_loop
        return self._client

    async def _post_chat_completion(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("VLM chat completion response must be a JSON object")
        return body

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
        image_format = "JPEG" if self._image_detail == "low" else "PNG"
        if image_format == "JPEG":
            image.save(buffer, format=image_format, quality=85, optimize=True)
            media_type = "image/jpeg"
        else:
            image.save(buffer, format=image_format)
            media_type = "image/png"
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{encoded}",
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
