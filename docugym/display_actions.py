from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

DisplayActionName = Literal[
    "toggle_pause",
    "force_narrate",
    "toggle_mute",
    "save_clip",
]


@dataclass(slots=True)
class DisplayActionTransition:
    """One action and the resulting pause/mute state after applying it."""

    action: DisplayActionName
    paused: bool
    muted: bool


def poll_display_actions(display: Any) -> list[DisplayActionName]:
    """Return validated pending display actions from a display-like object."""

    poll = getattr(display, "poll_actions", None)
    if not callable(poll):
        return []

    actions = poll()
    if not isinstance(actions, list):
        return []
    return actions


def build_action_transitions(
    actions: Iterable[DisplayActionName],
    *,
    paused: bool,
    muted: bool,
) -> list[DisplayActionTransition]:
    """Resolve display actions into sequential transitions for shared handling."""

    next_paused = paused
    next_muted = muted
    transitions: list[DisplayActionTransition] = []

    for action in actions:
        if action == "toggle_pause":
            next_paused = not next_paused
        elif action == "toggle_mute":
            next_muted = not next_muted

        transitions.append(
            DisplayActionTransition(
                action=action,
                paused=next_paused,
                muted=next_muted,
            )
        )

    return transitions
