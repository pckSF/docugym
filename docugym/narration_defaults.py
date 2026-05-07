from __future__ import annotations

DEFAULT_NARRATION_TEXT = "A pause. The creature gathers itself."


def validate_narration_config(
    *,
    narration_interval_seconds: float,
    min_gap_seconds: float,
    max_context_events: int,
    previous_narration_window: int,
) -> None:
    """Validate shared narration knobs for runtime and wrapper entrypoints."""

    if narration_interval_seconds <= 0:
        raise ValueError("narration_interval_seconds must be positive")
    if min_gap_seconds < 0:
        raise ValueError("min_gap_seconds must be non-negative")
    if max_context_events <= 0:
        raise ValueError("max_context_events must be positive")
    if previous_narration_window <= 0:
        raise ValueError("previous_narration_window must be positive")
