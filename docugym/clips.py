"""Helpers for persisting shareable frame+narration snapshot artifacts.

These utilities back keyboard-driven clip capture in runtime and wrapper flows,
producing deterministic PNG/TXT pairs for quick qualitative review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

from docugym.image_io import save_frame_png

if TYPE_CHECKING:
    import numpy as np

_CLIP_COUNTER = count()


def save_clip_snapshot(
    *,
    frame: np.ndarray,
    step: int,
    narration: str,
    out_dir: Path = Path("out/clips"),
) -> tuple[Path, Path]:
    """Save one frame and narration text as a timestamped snapshot pair.

    Args:
        frame: RGB/RGBA frame to persist as a PNG snapshot.
        step: Environment step used for deterministic filename labeling.
        narration: Narration text saved alongside the frame.
        out_dir: Destination directory for PNG/TXT snapshot files.

    Returns:
        Tuple of ``(frame_png_path, narration_text_path)``.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    stem = f"clip-step-{step:06d}-{timestamp}-{next(_CLIP_COUNTER):04d}"
    frame_path = out_dir / f"{stem}.png"
    narration_path = out_dir / f"{stem}.txt"

    save_frame_png(frame=frame, path=frame_path)
    narration_path.write_text(f"{narration.strip()}\n", encoding="utf-8")
    return frame_path, narration_path
