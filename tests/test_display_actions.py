from __future__ import annotations

from typing import Any

from docugym.display_actions import build_action_transitions, poll_display_actions


class FakeDisplay:
    def __init__(self, actions: Any) -> None:
        self._actions = actions

    def poll_actions(self) -> Any:
        return self._actions


def test_poll_display_actions_returns_empty_when_poll_missing() -> None:
    assert poll_display_actions(object()) == []


def test_poll_display_actions_validates_list_payload() -> None:
    assert poll_display_actions(FakeDisplay(actions=["toggle_pause"])) == [
        "toggle_pause"
    ]
    assert poll_display_actions(FakeDisplay(actions="toggle_pause")) == []


def test_build_action_transitions_preserves_toggle_order() -> None:
    transitions = build_action_transitions(
        [
            "toggle_pause",
            "toggle_mute",
            "toggle_pause",
            "force_narrate",
        ],
        paused=False,
        muted=False,
    )

    assert [item.paused for item in transitions] == [True, True, False, False]
    assert [item.muted for item in transitions] == [False, True, True, True]
    assert transitions[-1].action == "force_narrate"
