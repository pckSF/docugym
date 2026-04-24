from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Self, cast

from PIL import Image
import numpy as np

from docugym.narrator import NarrationContext, VLMNarrator


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    def __init__(
        self, capture: dict[str, Any], status_codes: list[int] | None = None
    ) -> None:
        self._capture = capture
        self._status_codes = status_codes or [200]
        self._get_calls = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, tb

    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self._capture["post_url"] = url
        self._capture["post_json"] = json
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "A calm drift along the edge."}
                            ]
                        }
                    }
                ]
            }
        )

    async def get(self, url: str) -> _FakeResponse:
        self._capture.setdefault("get_urls", []).append(url)
        status = self._status_codes[min(self._get_calls, len(self._status_codes) - 1)]
        self._get_calls += 1
        return _FakeResponse({"data": []}, status_code=status)


def test_narrate_frame_sync_posts_multimodal_payload(monkeypatch) -> None:
    capture: dict[str, Any] = {}

    def fake_async_client(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(capture)

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    narrator = VLMNarrator(
        base_url="http://localhost:8000/v1",
        model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
        max_tokens=80,
        temperature=0.8,
        top_p=0.9,
        image_detail="low",
    )
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    text = narrator.narrate_frame_sync(
        frame=frame,
        context=NarrationContext(
            env_human_name="ALE Pong v5",
            previous_narration="",
            event_summary="episode step 60; reward +0.00; episode reward +0.00",
        ),
    )

    assert text == "A calm drift along the edge."
    assert capture["post_url"] == "http://localhost:8000/v1/chat/completions"

    payload = cast("dict[str, Any]", capture["post_json"])
    assert payload["model"] == "Qwen/Qwen3-VL-8B-Instruct-AWQ"

    messages = cast("list[dict[str, Any]]", payload["messages"])
    assert len(messages) == 2

    user_content = cast("list[dict[str, Any]]", messages[1]["content"])
    image_message = user_content[1]
    assert image_message["image_url"]["detail"] == "low"

    data_url = image_message["image_url"]["url"]
    assert isinstance(data_url, str)
    assert data_url.startswith("data:image/png;base64,")

    raw_bytes = base64.b64decode(data_url.split(",", maxsplit=1)[1])
    image = Image.open(BytesIO(raw_bytes))
    assert max(image.size) <= 384


def test_wait_until_ready_sync_polls_until_success(monkeypatch) -> None:
    capture: dict[str, Any] = {}

    def fake_async_client(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(capture, status_codes=[503, 503, 200])

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    narrator = VLMNarrator(
        base_url="http://localhost:8000/v1",
        model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
        max_tokens=80,
        temperature=0.8,
        top_p=0.9,
        image_detail="low",
    )

    ready = narrator.wait_until_ready_sync(
        timeout_seconds=2.0, poll_interval_seconds=0.01
    )

    assert ready is True
    get_urls = cast("list[str]", capture["get_urls"])
    assert len(get_urls) >= 3
    assert all(url == "http://localhost:8000/v1/models" for url in get_urls)
