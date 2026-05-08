"""Narration event formatting tests for compact context-string builders."""

from __future__ import annotations

from docugym.narration_events import (
    format_event_summary,
    humanize_env_id,
    join_previous_narrations,
    join_recent_events,
)


def test_humanize_env_id_replaces_delimiters() -> None:
    assert humanize_env_id("ALE/SpaceInvaders-v5") == "ALE SpaceInvaders v5"


def test_format_event_summary_numeric_fields() -> None:
    summary = format_event_summary(
        step=12,
        reward=1.5,
        episode_reward=7.0,
        visual_delta=8.2,
        triggers=["cadence", "visual_delta"],
    )

    assert "step 12" in summary
    assert "reward +1.50" in summary
    assert "episode reward +7.00" in summary
    assert "delta 8.20" in summary
    assert "triggers cadence,visual_delta" in summary


def test_format_event_summary_na_fields() -> None:
    summary = format_event_summary(
        step=3,
        reward=None,
        episode_reward=-2.0,
        visual_delta=None,
        triggers=["manual"],
    )

    assert "reward n/a" in summary
    assert "delta n/a" in summary
    assert "triggers manual" in summary


def test_join_context_helpers_skip_empty_parts() -> None:
    recent = join_recent_events(["a", "", "b"])
    previous = join_previous_narrations([" one ", "", "two"])

    assert recent == "a | b"
    assert previous == "one two"
