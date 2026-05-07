"""Shared display-action normalization used by runtime and wrapper loops.

The helpers convert raw action lists into deterministic state transitions so pause
and mute toggles behave identically across orchestration modes.
"""

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
    """Action plus the derived pause/mute state after applying it.

    Attributes:
        action: Action identifier emitted by the display layer.
        paused: Derived paused flag after processing this action.
        muted: Derived muted flag after processing this action.
    """

    action: DisplayActionName
    paused: bool
    muted: bool


def poll_display_actions(display: Any) -> list[DisplayActionName]:
    """Return validated pending display actions from a display-like object.

    Args:
        display: Object that may implement ``poll_actions``.

    Returns:
        Validated action list, or an empty list when unavailable/invalid.
    """

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
    """Resolve actions into sequential pause/mute state transitions.

    Transition objects are emitted in order so callers can apply side effects with
    the same semantics as a user pressing keys one by one.

    Args:
        actions: Ordered action sequence to apply.
        paused: Initial paused state.
        muted: Initial muted state.

    Returns:
        Ordered transition objects with cumulative paused/muted state.
    """

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
