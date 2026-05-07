"""Keyframe gating heuristics used by runtime and wrapper narration flows.

The selector combines cadence, reward, episode-boundary, and visual-delta signals
to decide when narration is worth generating under bounded queue budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

import numpy as np

_DELTA_DOWNSAMPLE_STRIDE = 4


@dataclass(slots=True)
class KeyframeDecision:
    """Decision payload emitted when a frame qualifies for narration.

    Attributes:
        reasons: Trigger labels that caused selection (for example ``cadence`` or
            ``visual_delta``).
        visual_delta: Measured frame delta used by the visual trigger, or ``None``
            when no prior frame exists.
    """

    reasons: list[str]
    visual_delta: float | None


class KeyframeSelector:
    """Stateful gate that turns frame/reward signals into narration triggers.

    The selector tracks interval cadence and cooldown state so orchestrators can
    call ``consider`` on every step while still producing sparse, meaningful
    narration candidates.
    """

    def __init__(
        self,
        *,
        interval_seconds: float,
        min_gap_seconds: float,
        reward_spike_threshold: float,
        pixel_delta_threshold: float,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """Initialize trigger thresholds and selector state.

        Args:
            interval_seconds: Baseline cadence interval between trigger checks.
            min_gap_seconds: Cooldown between accepted narration candidates.
            reward_spike_threshold: Absolute reward threshold trigger.
            pixel_delta_threshold: Mean pixel-delta threshold trigger.
            clock: Time source used for cadence/cooldown bookkeeping.

        Raises:
            ValueError: If cadence or cooldown bounds are invalid.
        """

        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if min_gap_seconds < 0:
            raise ValueError("min_gap_seconds must be non-negative")

        self._interval_seconds = interval_seconds
        self._min_gap_seconds = min_gap_seconds
        self._reward_spike_threshold = reward_spike_threshold
        self._pixel_delta_threshold = pixel_delta_threshold
        self._clock = clock

        now = self._clock()
        self._last_interval_ts = now
        self._last_narration_ts = float("-inf")
        self._previous_frame: np.ndarray | None = None

    def reset(
        self,
        *,
        previous_frame: np.ndarray | None = None,
        timestamp: float | None = None,
    ) -> None:
        """Reset cadence/cooldown state for a new episode or session.

        Args:
            previous_frame: Optional baseline frame used for next delta comparison.
            timestamp: Optional override for reset timestamp.
        """

        current_ts = self._clock() if timestamp is None else timestamp
        self._last_interval_ts = current_ts
        self._last_narration_ts = float("-inf")
        self._previous_frame = (
            _pixel_delta_sample(previous_frame) if previous_frame is not None else None
        )

    def consider(
        self,
        *,
        frame: np.ndarray,
        reward: float,
        terminated: bool,
        truncated: bool,
        timestamp: float | None = None,
    ) -> KeyframeDecision | None:
        """Evaluate whether a frame should become a narration candidate.

        Args:
            frame: Current RGB/RGBA frame.
            reward: Reward associated with the current step.
            terminated: Whether the environment terminated this step.
            truncated: Whether the environment truncated this step.
            timestamp: Optional override for current timestamp.

        Returns:
            ``KeyframeDecision`` when any trigger fires and cooldown permits;
            otherwise ``None``.
        """

        now = self._clock() if timestamp is None else timestamp
        reasons: list[str] = []
        visual_delta: float | None = None

        if now - self._last_interval_ts >= self._interval_seconds:
            reasons.append("cadence")
            self._last_interval_ts = now
        if abs(reward) > self._reward_spike_threshold:
            reasons.append("reward_spike")
        if terminated or truncated:
            reasons.append("episode_boundary")

        current_sample = _pixel_delta_sample(frame)
        if self._previous_frame is not None:
            visual_delta = mean_abs_pixel_delta(
                current_sample,
                self._previous_frame,
                downsample_stride=1,
            )
            if visual_delta > self._pixel_delta_threshold:
                reasons.append("visual_delta")
        self._previous_frame = current_sample

        if not reasons:
            return None
        if now - self._last_narration_ts < self._min_gap_seconds:
            return None

        return KeyframeDecision(reasons=reasons, visual_delta=visual_delta)

    def mark_narration_enqueued(self, *, timestamp: float | None = None) -> None:
        """Record acceptance of a narration candidate for cooldown tracking.

        Args:
            timestamp: Optional acceptance timestamp override.
        """

        self._last_narration_ts = self._clock() if timestamp is None else timestamp


def _pixel_delta_sample(frame: np.ndarray) -> np.ndarray:
    """Downsample to a contiguous RGB sample used by delta comparisons."""

    return np.ascontiguousarray(
        frame[::_DELTA_DOWNSAMPLE_STRIDE, ::_DELTA_DOWNSAMPLE_STRIDE, :3]
    )


def mean_abs_pixel_delta(
    current: np.ndarray,
    previous: np.ndarray,
    *,
    downsample_stride: int = _DELTA_DOWNSAMPLE_STRIDE,
) -> float:
    """Return mean absolute RGB pixel delta between two frames.

    Downsampling is used to reduce per-frame CPU cost because this metric is only
    a trigger heuristic, not a full perceptual-quality estimate.
    """

    if downsample_stride <= 0:
        raise ValueError("downsample_stride must be positive")

    current_rgb = current[::downsample_stride, ::downsample_stride, :3].astype(
        np.float32,
        copy=False,
    )
    previous_rgb = previous[::downsample_stride, ::downsample_stride, :3].astype(
        np.float32,
        copy=False,
    )
    return float(np.mean(np.abs(current_rgb - previous_rgb)))
