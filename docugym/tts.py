from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any, AsyncIterator

import numpy as np

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class SpeechSentence:
    """Sentence-level synthesis output for subtitle and audio playback."""

    graphemes: str
    chunks: list[np.ndarray]


class KokoroTTS:
    """Kokoro-backed TTS engine that yields sentence-level audio chunks."""

    def __init__(
        self,
        *,
        voice: str,
        speed: float,
        sample_rate: int = 24_000,
        lang_code: str = "b",
        chunk_frames: int = 4096,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")

        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        self._lang_code = lang_code
        self._chunk_frames = chunk_frames
        self._pipeline: Any | None = None

    async def speak(self, text: str) -> AsyncIterator[SpeechSentence]:
        """Asynchronously synthesize text into sentence-level audio outputs."""

        sentences = await asyncio.to_thread(self._synthesize_sentences, text)
        for sentence in sentences:
            yield sentence

    def speak_sync(self, text: str) -> list[SpeechSentence]:
        """Synchronous wrapper around ``speak`` for non-async runtime loops."""

        async def _collect() -> list[SpeechSentence]:
            return [sentence async for sentence in self.speak(text)]

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_collect())

        raise RuntimeError(
            "speak_sync cannot be used from a running event loop; await speak instead."
        )

    def _synthesize_sentences(self, text: str) -> list[SpeechSentence]:
        pipeline = self._get_pipeline()
        outputs: list[SpeechSentence] = []

        for sentence in self._split_sentences(text):
            chunks = self._synthesize_sentence_chunks(pipeline, sentence)
            if not chunks:
                continue
            outputs.append(SpeechSentence(graphemes=sentence, chunks=chunks))

        return outputs

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        try:
            from kokoro import KPipeline
        except ImportError as exc:  # pragma: no cover - optional runtime dep
            raise RuntimeError(
                "kokoro is required for voiced narration. Install kokoro or run "
                "with --no-voice."
            ) from exc

        self._pipeline = KPipeline(lang_code=self._lang_code)
        return self._pipeline

    def _synthesize_sentence_chunks(
        self,
        pipeline: Any,
        sentence: str,
    ) -> list[np.ndarray]:
        sentence_chunks: list[np.ndarray] = []
        generator = pipeline(sentence, voice=self._voice, speed=self._speed)

        for item in generator:
            audio = self._extract_audio(item)
            if audio is None or audio.size == 0:
                continue
            sentence_chunks.extend(self._chunk_audio(audio))

        return sentence_chunks

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []

        return [
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY_RE.split(normalized)
            if sentence.strip()
        ]

    @staticmethod
    def _extract_audio(item: Any) -> np.ndarray | None:
        audio: Any | None = None

        if isinstance(item, (tuple, list)) and len(item) >= 3:
            audio = item[2]
        elif isinstance(item, dict):
            audio = item.get("audio")

        if audio is None:
            return None

        normalized = np.asarray(audio, dtype=np.float32).reshape(-1)
        return normalized

    def _chunk_audio(self, audio: np.ndarray) -> list[np.ndarray]:
        if audio.size == 0:
            return []

        return [
            audio[start : start + self._chunk_frames]
            for start in range(0, int(audio.size), self._chunk_frames)
        ]
