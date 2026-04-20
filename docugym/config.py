from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class RunSettings(BaseModel):
    """Runtime settings for environment stepping and pacing."""

    env_id: str = "ALE/SpaceInvaders-v5"
    env_kwargs: dict[str, Any] = Field(default_factory=dict)
    seed: int = 42
    fps: int = 60
    max_episodes: int = 10


class AgentSettings(BaseModel):
    """Agent selection and model source settings."""

    kind: Literal["sb3", "random", "scripted"] = "sb3"
    sb3_repo_id: str = "sb3/ppo-SpaceInvadersNoFrameskip-v4"
    sb3_filename: str = "ppo-SpaceInvadersNoFrameskip-v4.zip"


class VLMSettings(BaseModel):
    """Vision-language model server and sampling settings."""

    base_url: str = "http://localhost:8000/v1"
    model: str = "Qwen/Qwen3-VL-8B-Instruct-AWQ"
    max_tokens: int = 80
    temperature: float = 0.8
    top_p: float = 0.9
    image_detail: Literal["low", "high", "auto"] = "low"


class NarrationSettings(BaseModel):
    """Controls for narration trigger cadence and context."""

    interval_seconds: float = 3.0
    min_gap_seconds: float = 1.5
    reward_spike_threshold: float = 5.0
    pixel_delta_threshold: float = 8.0
    max_context_events: int = 3
    previous_narration_window: int = 2


class KokoroSettings(BaseModel):
    """Kokoro voice and synthesis output settings."""

    voice: str = "bm_george"
    speed: float = 0.95
    sample_rate: int = 24_000


class XTTSSettings(BaseModel):
    """Optional XTTS settings for alternate synthesis backends."""

    speaker_wav: str = "data/voices/british_narrator.wav"


class TTSSettings(BaseModel):
    """Text-to-speech backend configuration."""

    engine: Literal["kokoro", "xtts", "chatterbox"] = "kokoro"
    kokoro: KokoroSettings = Field(default_factory=KokoroSettings)
    xtts: XTTSSettings = Field(default_factory=XTTSSettings)


class DisplaySettings(BaseModel):
    """Window and subtitle rendering settings."""

    window_scale: int = 3
    subtitle_font: str = "DejaVu Sans"
    subtitle_size: int = 22
    hud: bool = True


class RecordingSettings(BaseModel):
    """Optional recording output controls."""

    enabled: bool = False
    out_path: str = "out/session.mp4"


class AppSettings(BaseSettings):
    """Top-level configuration model loaded from YAML and environment."""

    run: RunSettings = Field(default_factory=RunSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)
    narration: NarrationSettings = Field(default_factory=NarrationSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    display: DisplaySettings = Field(default_factory=DisplaySettings)
    recording: RecordingSettings = Field(default_factory=RecordingSettings)

    model_config = SettingsConfigDict(
        env_prefix="DOCUGYM_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    _yaml_path: ClassVar[Path] = DEFAULT_CONFIG_PATH

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = getattr(settings_cls, "_yaml_path", cls._yaml_path)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
            file_secret_settings,
        )


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppSettings:
    """Load app settings from YAML, overridden by environment variables."""

    yaml_path = Path(config_path)

    class SettingsWithYaml(AppSettings):
        _yaml_path: ClassVar[Path] = yaml_path

    return SettingsWithYaml()
