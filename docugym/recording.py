"""FFmpeg-backed recording utilities for synchronized gameplay session capture.

The recorder streams video frames and mirrors narration audio into an aligned PCM
track, then muxes both streams into a final MP4 artifact at session shutdown.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import threading
from time import perf_counter
from typing import Any, cast

import numpy as np

logger = logging.getLogger(__name__)

_SILENCE_BLOCK = np.zeros(4096, dtype=np.float32)


class FFmpegSessionRecorder:
    """Record rendered gameplay and narration audio into an MP4 artifact.

    Frames are streamed to ffmpeg as raw ``rgb24`` video while narration chunks are
    mirrored into a timestamp-aligned float32 mono PCM buffer. At shutdown, the
    encoded video and synthesized PCM track are muxed into a final MP4 file.

    The recorder is resilient to variable-latency narration chunks by inserting
    silence so the output timeline aligns with session timestamps.
    """

    def __init__(
        self,
        *,
        out_path: Path,
        fps: int,
        sample_rate: int,
        ffmpeg_binary: str = "ffmpeg",
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        resolved_ffmpeg = shutil.which(ffmpeg_binary)
        if resolved_ffmpeg is None:
            raise RuntimeError(
                "ffmpeg is required for recording but was not found in PATH."
            )

        self._out_path = out_path
        self._fps = fps
        self._sample_rate = sample_rate
        self._ffmpeg_binary = resolved_ffmpeg

        self._tmp_dir = TemporaryDirectory(prefix="docugym-recording-")
        tmp_path = Path(self._tmp_dir.name)
        self._video_path = tmp_path / "video.mp4"
        self._audio_path = tmp_path / "audio.f32le"
        self._audio_file = self._audio_path.open("wb")

        self._video_process: subprocess.Popen[bytes] | None = None
        self._video_stderr_chunks: list[bytes] = []
        self._video_stderr_thread: threading.Thread | None = None
        self._frame_shape: tuple[int, int] | None = None
        self._frame_count = 0
        self._audio_samples_written = 0
        self._started_at = perf_counter()
        self._closed = False

    def write_video_frame(self, frame: np.ndarray) -> None:
        """Append one rendered frame to the recording stream.

        Args:
            frame: RGB/RGBA frame with shape ``(H, W, C)``.

        Raises:
            RuntimeError: If recorder is closed or ffmpeg process is unavailable.
            ValueError: If frame shape changes mid-session.
        """

        if self._closed:
            raise RuntimeError("Cannot write video frame after recorder closure")

        frame_rgb = self._normalize_frame(frame)
        height, width, _ = frame_rgb.shape

        if self._frame_shape is None:
            self._frame_shape = (height, width)
            self._start_video_encoder(width=width, height=height)
        elif self._frame_shape != (height, width):
            raise ValueError(
                "Recording frame size changed mid-session. "
                f"Expected {self._frame_shape}, got {(height, width)}"
            )

        if self._video_process is None or self._video_process.stdin is None:
            raise RuntimeError("Video encoder process is not available")

        try:
            self._video_process.stdin.write(memoryview(cast("Any", frame_rgb)))
        except BrokenPipeError as exc:
            raise RuntimeError(
                "ffmpeg video encoder closed unexpectedly while recording"
            ) from exc

        self._frame_count += 1

    def write_audio_chunk(self, chunk: np.ndarray, *, timestamp: float) -> None:
        """Mirror one narration chunk into the recording audio timeline.

        Args:
            chunk: Mono audio samples for one synthesized chunk.
            timestamp: Monotonic timestamp associated with chunk emission.

        Notes:
            Calls after recorder closure are ignored so teardown paths can remain
            straightforward.
        """

        if self._closed:
            return

        normalized = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if normalized.size == 0:
            return

        offset_seconds = max(0.0, timestamp - self._started_at)
        target_samples = int(round(offset_seconds * self._sample_rate))
        if target_samples > self._audio_samples_written:
            self._write_silence(target_samples - self._audio_samples_written)

        self._audio_file.write(normalized.tobytes())
        self._audio_samples_written += int(normalized.size)

    def close(self, *, end_timestamp: float) -> Path | None:
        """Finalize recording and return saved output path when available.

        Args:
            end_timestamp: Monotonic end timestamp used for timeline padding.

        Returns:
            Output MP4 path when frames were recorded; otherwise ``None``.
        """

        if self._closed:
            return self._out_path if self._out_path.exists() else None

        self._closed = True

        try:
            if self._frame_count == 0:
                return None

            target_duration_seconds = max(
                0.0,
                end_timestamp - self._started_at,
                self._frame_count / float(self._fps),
            )
            target_samples = int(round(target_duration_seconds * self._sample_rate))
            if target_samples > self._audio_samples_written:
                self._write_silence(target_samples - self._audio_samples_written)

            self._audio_file.close()
            self._finalize_video_encoder()
            self._mux_audio_video()
            logger.info("Saved recording to %s", self._out_path)
            return self._out_path
        finally:
            if not self._audio_file.closed:
                self._audio_file.close()
            self._tmp_dir.cleanup()

    def _start_video_encoder(self, *, width: int, height: int) -> None:
        command = [
            self._ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            str(self._fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(self._video_path),
        ]
        self._video_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._video_stderr_thread = threading.Thread(
            target=self._drain_video_stderr,
            name="docugym-ffmpeg-stderr",
            daemon=True,
        )
        self._video_stderr_thread.start()

    def _finalize_video_encoder(self) -> None:
        process = self._video_process
        if process is None:
            raise RuntimeError("Video encoder never started")
        if process.stdin is None:
            raise RuntimeError("Video encoder stdin unavailable")

        process.stdin.close()
        return_code = process.wait()
        if self._video_stderr_thread is not None:
            self._video_stderr_thread.join(timeout=1.0)
        stderr = b"".join(self._video_stderr_chunks)
        if return_code != 0:
            raise RuntimeError(self._format_ffmpeg_error("video encoding", stderr))

    def _drain_video_stderr(self) -> None:
        process = self._video_process
        if process is None or process.stderr is None:
            return

        while True:
            chunk = process.stderr.read(4096)
            if not chunk:
                return
            self._video_stderr_chunks.append(chunk)

    def _mux_audio_video(self) -> None:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            self._ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(self._video_path),
            "-f",
            "f32le",
            "-ar",
            str(self._sample_rate),
            "-ac",
            "1",
            "-i",
            str(self._audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(self._out_path),
        ]

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                self._format_ffmpeg_error(
                    "audio/video muxing", completed.stderr.encode("utf-8")
                )
            )

    def _write_silence(self, sample_count: int) -> None:
        if sample_count <= 0:
            return

        remaining = sample_count
        while remaining > 0:
            take = min(remaining, _SILENCE_BLOCK.size)
            self._audio_file.write(memoryview(cast("Any", _SILENCE_BLOCK[:take])))
            remaining -= take

        self._audio_samples_written += sample_count

    @staticmethod
    def _normalize_frame(frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 3 or frame.shape[2] < 3:
            raise ValueError(
                "Recorder expects HxWx3 frame data for rgb_array rendering."
            )

        frame_rgb = frame[:, :, :3]
        if frame_rgb.dtype != np.uint8:
            frame_rgb = np.clip(frame_rgb, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(frame_rgb)

    @staticmethod
    def _format_ffmpeg_error(operation: str, stderr: bytes) -> str:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if stderr_text:
            return f"ffmpeg failed during {operation}: {stderr_text}"
        return f"ffmpeg failed during {operation}"
