from __future__ import annotations

from typing import Iterable, Sequence


def humanize_env_id(env_id: str) -> str:
    """Convert env id to a human-readable scene label."""

    return env_id.replace("/", " ").replace("-", " ")


def format_event_summary(
    *,
    step: int,
    reward: float | None,
    episode_reward: float,
    visual_delta: float | None,
    triggers: Sequence[str],
) -> str:
    """Build stable event-summary text used in narrator context windows."""

    reward_text = "n/a" if reward is None else f"{reward:+.2f}"
    delta_text = "n/a" if visual_delta is None else f"{visual_delta:.2f}"
    trigger_text = ",".join(triggers)

    return (
        f"step {step}; reward {reward_text}; episode reward "
        f"{episode_reward:+.2f}; delta {delta_text}; triggers {trigger_text}"
    )


def join_recent_events(events: Iterable[str]) -> str:
    """Join recent events into one compact narration context string."""

    return " | ".join(event for event in events if event)


def join_previous_narrations(narrations: Iterable[str]) -> str:
    """Join prior narration snippets for continuity prompts."""

    return " ".join(part.strip() for part in narrations if part).strip()
