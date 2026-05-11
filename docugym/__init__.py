"""Public package exports for installed DocuGym library users."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from docugym.config import (
        AgentSettings,
        AppSettings,
        DisplaySettings,
        KokoroSettings,
        NarrationSettings,
        RecordingSettings,
        RunSettings,
        TTSSettings,
        VLMSettings,
        XTTSSettings,
        load_settings,
    )
    from docugym.narrator import NarrationContext, VLMNarrator
    from docugym.prompts import (
        DEFAULT_SYSTEM_PROMPT,
        get_system_prompt,
        reset_system_prompt,
        set_system_prompt,
    )
    from docugym.runtime import RunResult, run_session, run_session_sync
    from docugym.tune import PromptTuningSample, run_prompt_tuning
    from docugym.wrapper import (
        AudioChunkCallback,
        DocuWrapper,
        NarrationCallback,
        StatusCallback,
        SubtitleCallback,
        docuwrapper,
    )

__version__ = "0.1.0"

_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentSettings": ("docugym.config", "AgentSettings"),
    "AppSettings": ("docugym.config", "AppSettings"),
    "AudioChunkCallback": ("docugym.wrapper", "AudioChunkCallback"),
    "DEFAULT_SYSTEM_PROMPT": ("docugym.prompts", "DEFAULT_SYSTEM_PROMPT"),
    "DisplaySettings": ("docugym.config", "DisplaySettings"),
    "DocuWrapper": ("docugym.wrapper", "DocuWrapper"),
    "KokoroSettings": ("docugym.config", "KokoroSettings"),
    "NarrationCallback": ("docugym.wrapper", "NarrationCallback"),
    "NarrationContext": ("docugym.narrator", "NarrationContext"),
    "NarrationSettings": ("docugym.config", "NarrationSettings"),
    "PromptTuningSample": ("docugym.tune", "PromptTuningSample"),
    "RecordingSettings": ("docugym.config", "RecordingSettings"),
    "RunResult": ("docugym.runtime", "RunResult"),
    "RunSettings": ("docugym.config", "RunSettings"),
    "StatusCallback": ("docugym.wrapper", "StatusCallback"),
    "SubtitleCallback": ("docugym.wrapper", "SubtitleCallback"),
    "TTSSettings": ("docugym.config", "TTSSettings"),
    "VLMNarrator": ("docugym.narrator", "VLMNarrator"),
    "VLMSettings": ("docugym.config", "VLMSettings"),
    "XTTSSettings": ("docugym.config", "XTTSSettings"),
    "docuwrapper": ("docugym.wrapper", "docuwrapper"),
    "get_system_prompt": ("docugym.prompts", "get_system_prompt"),
    "load_settings": ("docugym.config", "load_settings"),
    "reset_system_prompt": ("docugym.prompts", "reset_system_prompt"),
    "run_prompt_tuning": ("docugym.tune", "run_prompt_tuning"),
    "run_session": ("docugym.runtime", "run_session"),
    "run_session_sync": ("docugym.runtime", "run_session_sync"),
    "set_system_prompt": ("docugym.prompts", "set_system_prompt"),
}

__all__ = [
    "__version__",
    "AgentSettings",
    "AppSettings",
    "AudioChunkCallback",
    "DEFAULT_SYSTEM_PROMPT",
    "DisplaySettings",
    "DocuWrapper",
    "KokoroSettings",
    "NarrationCallback",
    "NarrationContext",
    "NarrationSettings",
    "PromptTuningSample",
    "RecordingSettings",
    "RunResult",
    "RunSettings",
    "StatusCallback",
    "SubtitleCallback",
    "TTSSettings",
    "VLMNarrator",
    "VLMSettings",
    "XTTSSettings",
    "docuwrapper",
    "get_system_prompt",
    "load_settings",
    "reset_system_prompt",
    "run_prompt_tuning",
    "run_session",
    "run_session_sync",
    "set_system_prompt",
]


def __getattr__(name: str) -> Any:
    """Load public exports on demand to keep lightweight imports quiet.

    Args:
        name: Public export requested from the package root.

    Returns:
        Exported object resolved from its implementation module.

    Raises:
        AttributeError: If ``name`` is not part of DocuGym's public root API.
    """

    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return sorted attributes for interactive discovery.

    Returns:
        Built-in module attributes plus public root exports.
    """

    return sorted({*globals(), *__all__})
