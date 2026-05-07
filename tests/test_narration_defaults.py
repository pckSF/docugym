from __future__ import annotations

import pytest

from docugym.narration_defaults import (
    DEFAULT_NARRATION_TEXT,
    validate_narration_config,
)


def test_validate_narration_config_accepts_valid_values() -> None:
    validate_narration_config(
        narration_interval_seconds=3.0,
        min_gap_seconds=0.0,
        max_context_events=3,
        previous_narration_window=2,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "narration_interval_seconds": 0.0,
                "min_gap_seconds": 0.0,
                "max_context_events": 3,
                "previous_narration_window": 2,
            },
            "narration_interval_seconds must be positive",
        ),
        (
            {
                "narration_interval_seconds": 1.0,
                "min_gap_seconds": -1.0,
                "max_context_events": 3,
                "previous_narration_window": 2,
            },
            "min_gap_seconds must be non-negative",
        ),
        (
            {
                "narration_interval_seconds": 1.0,
                "min_gap_seconds": 0.0,
                "max_context_events": 0,
                "previous_narration_window": 2,
            },
            "max_context_events must be positive",
        ),
        (
            {
                "narration_interval_seconds": 1.0,
                "min_gap_seconds": 0.0,
                "max_context_events": 3,
                "previous_narration_window": 0,
            },
            "previous_narration_window must be positive",
        ),
    ],
)
def test_validate_narration_config_rejects_invalid_values(
    kwargs: dict[str, float | int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_narration_config(**kwargs)


def test_default_narration_text_is_non_empty() -> None:
    assert DEFAULT_NARRATION_TEXT.strip()
