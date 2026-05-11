"""Shared image persistence helpers for frame artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path


def save_frame_png(frame: np.ndarray, path: Path) -> None:
    """Persist an RGB/RGBA frame as a PNG, normalizing dtype for Pillow."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError("Pillow is required to save PNG frame artifacts.") from exc

    frame_to_save = frame[:, :, :3]
    if frame_to_save.dtype != np.uint8:
        frame_to_save = np.clip(frame_to_save, 0, 255).astype(np.uint8)

    Image.fromarray(frame_to_save).save(path, format="PNG")
