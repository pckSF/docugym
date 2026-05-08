"""Shared narration defaults and validation constraints.

Keeping this in a tiny module avoids drift between runtime and wrapper knobs and
ensures both paths fail fast on invalid cadence-related values.
"""

from __future__ import annotations

DEFAULT_NARRATION_TEXT = "A pause. The creature gathers itself."


def validate_narration_config(
    *,
    narration_interval_seconds: float,
    min_gap_seconds: float,
    max_context_events: int,
    previous_narration_window: int,
) -> None:
    """Validate narration cadence/context bounds shared across entrypoints.

    Args:
        narration_interval_seconds: Target narration cadence in seconds.
        min_gap_seconds: Minimum spacing between accepted narration events.
        max_context_events: Maximum count of recent events in narrator context.
        previous_narration_window: Number of previous lines retained for context.

    Raises:
        ValueError: If any duration/count argument falls outside allowed bounds.
    """

    if narration_interval_seconds <= 0:
        raise ValueError("narration_interval_seconds must be positive")
    if min_gap_seconds < 0:
        raise ValueError("min_gap_seconds must be non-negative")
    if max_context_events <= 0:
        raise ValueError("max_context_events must be positive")
    if previous_narration_window <= 0:
        raise ValueError("previous_narration_window must be positive")
