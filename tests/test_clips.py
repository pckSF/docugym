from __future__ import annotations

import numpy as np

from docugym.clips import save_clip_snapshot


def test_save_clip_snapshot_writes_png_and_text(tmp_path) -> None:
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    frame[:, :, 1] = 127

    frame_path, narration_path = save_clip_snapshot(
        frame=frame,
        step=12,
        narration="The patient traveller drifts onward.",
        out_dir=tmp_path,
    )

    assert frame_path.suffix == ".png"
    assert narration_path.suffix == ".txt"
    assert frame_path.exists()
    assert narration_path.exists()
    assert narration_path.read_text(encoding="utf-8") == (
        "The patient traveller drifts onward.\n"
    )


def test_save_clip_snapshot_normalizes_non_uint8_frames(tmp_path) -> None:
    frame = np.full((4, 6, 3), fill_value=400.0, dtype=np.float32)

    frame_path, narration_path = save_clip_snapshot(
        frame=frame,
        step=2,
        narration="A pause.",
        out_dir=tmp_path,
    )

    assert frame_path.exists()
    assert narration_path.exists()
