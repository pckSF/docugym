"""Public prompt customization helpers for narration style control."""

from __future__ import annotations

from textwrap import dedent

DEFAULT_SYSTEM_PROMPT = dedent(
    """
        You are a calm, wonder-filled nature-documentary narrator in the tradition of
        BBC wildlife programmes. You are watching a game on screen and narrating it as
        if it were a rare scene from the natural world. Observe the creature (or vessel,
        vehicle, or figure) on screen with the same reverence you would give a pangolin
        or a lyrebird.

        Rules:
        - 1 to 2 sentences, present tense, British phrasing.
        - Hushed, measured, slightly awed. Short clauses. No exclamation marks.
        - Use biology / ecology metaphors where natural: instinct, territory,
            courtship, peril, lineage, survival, the edge of exhaustion.
        - Do not name the game. Do not mention pixels, screens, scores, or controllers.
        - Do not name real people. You are a narrator, not the narrator.
        - If nothing has changed, say so gently (e.g., "A pause. The creature gathers
            itself.").
        """
).strip()

_active_system_prompt = DEFAULT_SYSTEM_PROMPT


def get_system_prompt() -> str:
    """Return the active default narration system prompt.

    Returns:
        Process-wide system prompt used by narrators without an instance
        override.
    """

    return _active_system_prompt


def set_system_prompt(prompt: str) -> None:
    """Set the process-wide default system prompt used by new narrator calls.

    Args:
        prompt: Non-empty system prompt text.

    Raises:
        ValueError: If ``prompt`` is blank after trimming whitespace.
    """

    normalized = prompt.strip()
    if not normalized:
        raise ValueError("system prompt must not be empty")

    global _active_system_prompt  # noqa: PLW0603

    _active_system_prompt = normalized


def reset_system_prompt() -> None:
    """Restore the built-in narration system prompt."""

    global _active_system_prompt  # noqa: PLW0603

    _active_system_prompt = DEFAULT_SYSTEM_PROMPT
