from __future__ import annotations

import sys
import types

import numpy as np

from docugym.tts import KokoroTTS


class FakePipeline:
    def __init__(self, lang_code: str) -> None:
        self.lang_code = lang_code
        self.calls: list[tuple[str, str, float]] = []

    def __call__(self, text: str, *, voice: str, speed: float):
        self.calls.append((text, voice, speed))
        audio = np.arange(10, dtype=np.float32)
        return [(text, "ignored", audio)]


def test_kokoro_tts_speak_sync_splits_sentences_and_chunks(monkeypatch) -> None:
    created: dict[str, FakePipeline] = {}

    def fake_factory(*, lang_code: str) -> FakePipeline:
        pipeline = FakePipeline(lang_code=lang_code)
        created["pipeline"] = pipeline
        return pipeline

    kokoro_module = types.ModuleType("kokoro")
    setattr(kokoro_module, "KPipeline", fake_factory)
    monkeypatch.setitem(sys.modules, "kokoro", kokoro_module)

    tts = KokoroTTS(
        voice="bm_george",
        speed=0.95,
        sample_rate=24_000,
        chunk_frames=4,
    )

    sentences = tts.speak_sync("The first line. The second line?")

    assert [sentence.graphemes for sentence in sentences] == [
        "The first line.",
        "The second line?",
    ]
    assert [len(sentence.chunks) for sentence in sentences] == [3, 3]

    pipeline = created["pipeline"]
    assert pipeline.lang_code == "b"
    assert pipeline.calls == [
        ("The first line.", "bm_george", 0.95),
        ("The second line?", "bm_george", 0.95),
    ]


def test_kokoro_tts_speak_sync_handles_blank_text(monkeypatch) -> None:
    kokoro_module = types.ModuleType("kokoro")
    setattr(kokoro_module, "KPipeline", lambda **_kwargs: FakePipeline(lang_code="b"))
    monkeypatch.setitem(sys.modules, "kokoro", kokoro_module)

    tts = KokoroTTS(voice="bm_george", speed=1.0)

    assert tts.speak_sync("   ") == []
