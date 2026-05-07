"""Helpers for persisting shareable frame+narration snapshot artifacts.

These utilities back keyboard-driven clip capture in runtime and wrapper flows,
producing deterministic PNG/TXT pairs for quick qualitative review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from pathlib import Path

import numpy as np

_CLIP_COUNTER = count()


def _save_frame_png(frame: np.ndarray, path: Path) -> None:
    """Persist a frame as PNG, normalizing dtype for Pillow compatibility."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError("Pillow is required to save clip snapshots.") from exc

    frame_to_save = frame
    if frame_to_save.dtype != np.uint8:
        frame_to_save = np.clip(frame_to_save, 0, 255).astype(np.uint8)

    Image.fromarray(frame_to_save[:, :, :3]).save(path, format="PNG")


def save_clip_snapshot(
    *,
    frame: np.ndarray,
    step: int,
    narration: str,
    out_dir: Path = Path("out/clips"),
) -> tuple[Path, Path]:
    """Save one frame and narration text as a timestamped snapshot pair.

    Returns:
        Tuple of ``(frame_png_path, narration_text_path)``.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    stem = f"clip-step-{step:06d}-{timestamp}-{next(_CLIP_COUNTER):04d}"
    frame_path = out_dir / f"{stem}.png"
    narration_path = out_dir / f"{stem}.txt"

    _save_frame_png(frame=frame, path=frame_path)
    narration_path.write_text(f"{narration.strip()}\n", encoding="utf-8")
    return frame_path, narration_path
