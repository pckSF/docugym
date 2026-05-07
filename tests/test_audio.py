from __future__ import annotations

import numpy as np
import pytest

from docugym.audio import AudioOutput


def test_audio_output_callback_drains_enqueued_chunk() -> None:
    output = AudioOutput(sample_rate=24_000, max_queue_chunks=4)
    output.enqueue(np.array([0.25, 0.5], dtype=np.float32))

    outdata = np.zeros((4, 1), dtype=np.float32)
    output._callback(outdata, 4)

    assert outdata[:, 0].tolist() == pytest.approx([0.25, 0.5, 0.0, 0.0])


def test_audio_output_drops_oldest_chunk_when_queue_is_full() -> None:
    output = AudioOutput(sample_rate=24_000, max_queue_chunks=1)
    output.enqueue(np.array([0.1], dtype=np.float32))
    output.enqueue(np.array([0.2], dtype=np.float32))

    outdata = np.zeros((1, 1), dtype=np.float32)
    output._callback(outdata, 1)

    assert outdata[:, 0].tolist() == pytest.approx([0.2])
