"""Keyframe selector tests for cadence, cooldown, and visual-delta triggers."""

from __future__ import annotations

import numpy as np

from docugym.keyframes import KeyframeSelector


def test_keyframe_selector_triggers_cadence_and_reward() -> None:
    selector = KeyframeSelector(
        interval_seconds=1.0,
        min_gap_seconds=0.5,
        reward_spike_threshold=2.0,
        pixel_delta_threshold=50.0,
    )
    selector.reset(previous_frame=np.zeros((4, 4, 3), dtype=np.uint8), timestamp=0.0)

    decision = selector.consider(
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
        reward=3.5,
        terminated=False,
        truncated=False,
        timestamp=1.2,
    )

    assert decision is not None
    assert "cadence" in decision.reasons
    assert "reward_spike" in decision.reasons


def test_keyframe_selector_respects_cooldown_after_mark() -> None:
    selector = KeyframeSelector(
        interval_seconds=0.1,
        min_gap_seconds=1.0,
        reward_spike_threshold=0.1,
        pixel_delta_threshold=1.0,
    )
    selector.reset(previous_frame=np.zeros((4, 4, 3), dtype=np.uint8), timestamp=0.0)

    first = selector.consider(
        frame=np.ones((4, 4, 3), dtype=np.uint8),
        reward=1.0,
        terminated=False,
        truncated=False,
        timestamp=0.2,
    )
    assert first is not None

    selector.mark_narration_enqueued(timestamp=0.2)
    blocked = selector.consider(
        frame=np.ones((4, 4, 3), dtype=np.uint8) * 2,
        reward=1.0,
        terminated=False,
        truncated=False,
        timestamp=0.5,
    )

    assert blocked is None


def test_keyframe_selector_triggers_visual_delta() -> None:
    selector = KeyframeSelector(
        interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=999.0,
        pixel_delta_threshold=5.0,
    )
    selector.reset(previous_frame=np.zeros((4, 4, 3), dtype=np.uint8), timestamp=0.0)

    decision = selector.consider(
        frame=np.ones((4, 4, 3), dtype=np.uint8) * 255,
        reward=0.0,
        terminated=False,
        truncated=False,
        timestamp=0.1,
    )

    assert decision is not None
    assert decision.visual_delta is not None
    assert "visual_delta" in decision.reasons
