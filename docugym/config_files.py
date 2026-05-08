"""Resolve DocuGym configuration presets for source and installed usage.

The CLI and library both need default/preset YAML files to work when DocuGym is
installed into an environment and launched from outside the repository checkout.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

DEFAULT_CONFIG_NAME = "default"
RUNTIME_CONFIG_PRESET_NAMES: tuple[str, ...] = (
    "atari",
    "lunarlander",
    "carracing",
)
CONFIG_PRESET_NAMES: tuple[str, ...] = (
    DEFAULT_CONFIG_NAME,
    *RUNTIME_CONFIG_PRESET_NAMES,
)

_CONFIG_RESOURCE_DIR = "configs"
_SOURCE_CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


class ConfigNotFoundError(ValueError):
    """Raised when a config reference is neither a known preset nor a file."""


def _normalize_reference(config: str | Path | None) -> str:
    if config is None:
        return DEFAULT_CONFIG_NAME

    value = str(config).strip()
    return value or DEFAULT_CONFIG_NAME


def _preset_name_from_reference(config: str | Path | None) -> str | None:
    reference = _normalize_reference(config)
    if reference in CONFIG_PRESET_NAMES:
        return reference

    path = Path(reference)
    if len(path.parts) == 1 and path.suffix in {".yaml", ".yml"}:
        if path.stem in CONFIG_PRESET_NAMES:
            return path.stem

    if len(path.parts) == 2 and path.parts[0] == _CONFIG_RESOURCE_DIR:
        candidate = Path(path.parts[1])
        if (
            candidate.suffix in {".yaml", ".yml"}
            and candidate.stem in CONFIG_PRESET_NAMES
        ):
            return candidate.stem

    return None


def _available_presets_message() -> str:
    return ", ".join(CONFIG_PRESET_NAMES)


@contextmanager
def resolved_config_path(config: str | Path | None = None) -> Iterator[Path]:
    """Yield a filesystem path for a config preset name or explicit YAML path.

    Source-tree configs are preferred when present so local edits under `configs/`
    keep taking effect during development. Installed wheels fall back to bundled
    resources under `docugym/configs/`.

    Args:
        config: Preset name, `configs/<preset>.yaml` shorthand, explicit YAML
            path, or ``None`` for the default preset.

    Raises:
        ConfigNotFoundError: If the reference is not a known preset or existing
            YAML file, or if the packaged resource is missing.
    """

    reference = _normalize_reference(config)
    explicit_path = Path(reference)
    if explicit_path.exists():
        yield explicit_path
        return

    preset_name = _preset_name_from_reference(reference)
    if preset_name is None:
        raise ConfigNotFoundError(
            "Config must be an existing YAML file or one of these presets: "
            f"{_available_presets_message()}"
        )

    source_path = _SOURCE_CONFIG_DIR / f"{preset_name}.yaml"
    if source_path.exists():
        yield source_path
        return

    resource = resources.files("docugym").joinpath(
        _CONFIG_RESOURCE_DIR,
        f"{preset_name}.yaml",
    )
    if not resource.is_file():
        raise ConfigNotFoundError(
            f"Packaged config preset {preset_name!r} is missing from docugym."
        )

    with resources.as_file(resource) as packaged_path:
        yield packaged_path
