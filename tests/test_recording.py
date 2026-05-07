from __future__ import annotations

from io import BytesIO
import subprocess
from typing import TYPE_CHECKING

import numpy as np

from docugym.recording import FFmpegSessionRecorder

if TYPE_CHECKING:
    from pathlib import Path


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[object] = []
        self.closed = False

    def write(self, data: object) -> int:
        self.writes.append(data)
        if isinstance(data, memoryview):
            return data.nbytes
        if isinstance(data, bytes | bytearray):
            return len(data)
        return 0

    def close(self) -> None:
        self.closed = True


class FakeStderr(BytesIO):
    def __init__(self) -> None:
        super().__init__(b"warning line\n")
        self.read_calls = 0

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        return super().read(size)


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = FakeStdin()
        self.stderr = FakeStderr()

    def wait(self) -> int:
        return 0


def test_recorder_writes_memoryview_and_drains_ffmpeg_stderr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    process = FakeProcess()

    def fake_popen(*_args: object, **_kwargs: object) -> FakeProcess:
        return process

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("docugym.recording.shutil.which", lambda _binary: "ffmpeg")
    monkeypatch.setattr("docugym.recording.subprocess.Popen", fake_popen)
    monkeypatch.setattr("docugym.recording.subprocess.run", fake_run)

    recorder = FFmpegSessionRecorder(
        out_path=tmp_path / "session.mp4",
        fps=30,
        sample_rate=24_000,
    )

    recorder.write_video_frame(np.zeros((4, 6, 3), dtype=np.uint8))
    saved_path = recorder.close(end_timestamp=recorder._started_at + 0.1)

    assert saved_path == tmp_path / "session.mp4"
    assert process.stdin.closed is True
    assert isinstance(process.stdin.writes[0], memoryview)
    assert process.stderr.read_calls >= 1
