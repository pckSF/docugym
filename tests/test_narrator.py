"""Narrator client tests for payload shape, client reuse, and readiness polling."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any, Self, cast

from PIL import Image
import numpy as np
import pytest

from docugym.narrator import NarrationContext, VLMNarrator
from docugym.narration_defaults import DEFAULT_NARRATION_TEXT
from docugym.prompts import get_system_prompt, reset_system_prompt, set_system_prompt


class _FakeResponse:
    """Minimal HTTP-response stub with JSON payload and status simulation."""

    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    """Async HTTP-client stub capturing post/get calls for assertions."""

    def __init__(
        self, capture: dict[str, Any], status_codes: list[int] | None = None
    ) -> None:
        self._capture = capture
        self._status_codes = status_codes or [200]
        self._get_calls = 0
        self.is_closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, tb
        await self.aclose()

    async def aclose(self) -> None:
        self.is_closed = True

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
    assert data_url.startswith("data:image/jpeg;base64,")

    raw_bytes = base64.b64decode(data_url.split(",", maxsplit=1)[1])
    image = Image.open(BytesIO(raw_bytes))
    assert max(image.size) <= 384


def test_global_system_prompt_override_is_used(monkeypatch) -> None:
    capture: dict[str, Any] = {}

    def fake_async_client(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(capture)

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    set_system_prompt("Narrate with terse field notes.")
    try:
        narrator = VLMNarrator(
            base_url="http://localhost:8000/v1",
            model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
            max_tokens=80,
            temperature=0.8,
            top_p=0.9,
        )
        narrator.narrate_frame_sync(
            frame=np.zeros((8, 8, 3), dtype=np.uint8),
            context=NarrationContext(env_human_name="CartPole v1"),
        )
    finally:
        reset_system_prompt()

    payload = cast("dict[str, Any]", capture["post_json"])
    messages = cast("list[dict[str, Any]]", payload["messages"])
    assert messages[0]["content"] == "Narrate with terse field notes."


def test_instance_system_prompt_overrides_global_prompt(monkeypatch) -> None:
    capture: dict[str, Any] = {}

    def fake_async_client(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(capture)

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    set_system_prompt("Global prompt.")
    try:
        narrator = VLMNarrator(
            base_url="http://localhost:8000/v1",
            model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
            max_tokens=80,
            temperature=0.8,
            top_p=0.9,
            system_prompt="Instance prompt.",
        )
        narrator.narrate_frame_sync(
            frame=np.zeros((8, 8, 3), dtype=np.uint8),
            context=NarrationContext(env_human_name="CartPole v1"),
        )
    finally:
        reset_system_prompt()

    payload = cast("dict[str, Any]", capture["post_json"])
    messages = cast("list[dict[str, Any]]", payload["messages"])
    assert messages[0]["content"] == "Instance prompt."


def test_system_prompt_helpers_reject_blank_and_reset() -> None:
    original_prompt = get_system_prompt()

    with pytest.raises(ValueError, match="must not be empty"):
        set_system_prompt("   ")

    set_system_prompt("Temporary prompt.")
    assert get_system_prompt() == "Temporary prompt."

    reset_system_prompt()
    assert get_system_prompt() == original_prompt


def test_narrate_frame_reuses_async_client_until_closed(monkeypatch) -> None:
    capture: dict[str, Any] = {"clients": []}

    def fake_async_client(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        client = _FakeAsyncClient(capture)
        capture["clients"].append(client)
        return client

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    narrator = VLMNarrator(
        base_url="http://localhost:8000/v1",
        model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
        max_tokens=80,
        temperature=0.8,
        top_p=0.9,
        image_detail="low",
    )
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    context = NarrationContext(env_human_name="CartPole v1")

    async def run_twice() -> None:
        first = await narrator.narrate_frame(frame=frame, context=context)
        second = await narrator.narrate_frame(frame=frame, context=context)
        await narrator.aclose()
        assert first == second == "A calm drift along the edge."

    asyncio.run(run_twice())

    clients = cast("list[_FakeAsyncClient]", capture["clients"])
    assert len(clients) == 1
    assert clients[0].is_closed is True


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


class _FixedResponseClient:
    """Async client stub returning a fixed (possibly malformed) JSON body."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.is_closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, tb
        await self.aclose()

    async def aclose(self) -> None:
        self.is_closed = True

    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        del url, json
        return _FakeResponse(self._payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
    ],
)
def test_narrate_frame_sync_returns_fallback_on_malformed_response(
    monkeypatch, payload: dict[str, object]
) -> None:
    def fake_async_client(*_args: object, **_kwargs: object) -> _FixedResponseClient:
        return _FixedResponseClient(payload)

    monkeypatch.setattr("docugym.narrator.httpx.AsyncClient", fake_async_client)

    narrator = VLMNarrator(
        base_url="http://localhost:8000/v1",
        model="model",
        max_tokens=80,
        temperature=0.8,
        top_p=0.9,
    )

    text = narrator.narrate_frame_sync(
        frame=np.zeros((8, 8, 3), dtype=np.uint8),
        context=NarrationContext(env_human_name="Scene"),
    )

    assert text == DEFAULT_NARRATION_TEXT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tokens": 0},
        {"temperature": -0.1},
        {"top_p": 0.0},
        {"top_p": 1.5},
    ],
)
def test_narrator_rejects_invalid_sampling_params(kwargs: dict[str, Any]) -> None:
    base: dict[str, Any] = {
        "base_url": "http://localhost:8000/v1",
        "model": "model",
        "max_tokens": 80,
        "temperature": 0.8,
        "top_p": 0.9,
    }
    base.update(kwargs)

    with pytest.raises(ValueError):
        VLMNarrator(**base)
