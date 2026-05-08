"""Formatting helpers for compact, model-friendly narration context text.

Stable string formatting keeps narrator prompts comparable between sessions and
reduces accidental prompt drift when runtime internals evolve.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def humanize_env_id(env_id: str) -> str:
    """Convert environment id text into a human-readable scene label.

    Args:
        env_id: Gymnasium environment id.

    Returns:
        Readable scene label used in narration context prompts.
    """

    return env_id.replace("/", " ").replace("-", " ")


def format_event_summary(
    *,
    step: int,
    reward: float | None,
    episode_reward: float,
    visual_delta: float | None,
    triggers: Sequence[str],
) -> str:
    """Build a stable one-line event summary for narrator context windows.

    The output is intentionally compact and deterministic so prompt behavior is
    easier to compare across runs and model variants.

    Args:
        step: Environment step index at capture time.
        reward: Step reward, if one is available for this event.
        episode_reward: Episode return accumulated through this step.
        visual_delta: Mean absolute RGB delta relative to prior sampled frame.
        triggers: Trigger labels that caused narration candidate selection.

    Returns:
        Deterministic one-line context summary consumed by narrator prompts.
    """

    reward_text = "n/a" if reward is None else f"{reward:+.2f}"
    delta_text = "n/a" if visual_delta is None else f"{visual_delta:.2f}"
    trigger_text = ",".join(triggers)

    return (
        f"step {step}; reward {reward_text}; episode reward "
        f"{episode_reward:+.2f}; delta {delta_text}; triggers {trigger_text}"
    )


def join_recent_events(events: Iterable[str]) -> str:
    """Join recent events into one compact narration context string.

    Args:
        events: Iterable of event-summary strings.

    Returns:
        Pipe-separated context summary.
    """

    return " | ".join(event for event in events if event)


def join_previous_narrations(narrations: Iterable[str]) -> str:
    """Join prior narration snippets for continuity prompts.

    Args:
        narrations: Iterable of previous narration strings.

    Returns:
        Whitespace-normalized continuity context string.
    """

    return " ".join(part.strip() for part in narrations if part).strip()
