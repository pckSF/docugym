from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
import queue
from typing import Any

import numpy as np

from docugym.queue_utils import push_drop_oldest_sync

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AudioStats:
    """Runtime counters for audio queue behavior."""

    dropped_chunks: int = 0


class AudioOutput:
    """Queue-backed sounddevice output stream for low-latency mono playback."""

    def __init__(
        self,
        *,
        sample_rate: int = 24_000,
        channels: int = 1,
        dtype: str = "float32",
        blocksize: int = 0,
        latency: str = "low",
        max_queue_chunks: int = 256,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels != 1:
            raise ValueError("AudioOutput currently supports mono output only")

        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._blocksize = blocksize
        self._latency = latency
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_chunks)
        self._pending = np.empty(0, dtype=np.float32)
        self._stream: Any | None = None
        self._stats = AudioStats()

    @property
    def stats(self) -> AudioStats:
        """Return runtime audio queue counters."""

        return self._stats

    def start(self) -> None:
        """Start the underlying sounddevice output stream."""

        if self._stream is not None:
            return

        try:
            sd = importlib.import_module("sounddevice")
        except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dep
            raise RuntimeError(
                "sounddevice is required for voiced narration. Install sounddevice "
                "or run with --no-voice."
            ) from exc

        self._stream = sd.OutputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype=self._dtype,
            blocksize=self._blocksize,
            latency=self._latency,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop and close the output stream if it is active."""

        if self._stream is None:
            return

        self._stream.stop()
        self._stream.close()
        self._stream = None

    def enqueue(self, chunk: np.ndarray) -> None:
        """Queue a mono float32 chunk for callback playback.

        Oldest chunks are dropped when the queue is full to prioritize fresh audio.
        """

        normalized = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if normalized.size == 0:
            return

        dropped = push_drop_oldest_sync(self._queue, normalized)
        if dropped:
            self._stats.dropped_chunks += 1
            logger.debug("Dropped audio chunk due to sustained queue pressure")

    def clear(self) -> None:
        """Drop pending queued and buffered audio chunks immediately."""

        self._pending = np.empty(0, dtype=np.float32)
        while True:
            try:
                _ = self._queue.get_nowait()
            except queue.Empty:
                return

    def _callback(self, outdata: np.ndarray, frames: int, *_: object) -> None:
        outdata.fill(0.0)

        write_offset = 0
        while write_offset < frames:
            if self._pending.size == 0:
                try:
                    self._pending = self._queue.get_nowait()
                except queue.Empty:
                    break

            take = min(frames - write_offset, int(self._pending.size))
            outdata[write_offset : write_offset + take, 0] = self._pending[:take]
            self._pending = self._pending[take:]
            write_offset += take
