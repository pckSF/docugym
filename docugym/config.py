"""Pydantic configuration models and settings-source composition for DocuGym.

The configuration tree is shared by CLI, runtime, and wrapper entrypoints so
operational defaults live in YAML while environment variables can override values
for CI and deployment-specific runs.
"""

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
    """Runtime settings for environment stepping and pacing.

    Attributes:
        env_id: Default Gymnasium environment id.
        env_kwargs: Extra kwargs forwarded to ``gym.make``.
        seed: Default reset/action-space seed.
        fps: Target display framerate.
        max_episodes: Default episode cap for CLI run mode.
    """

    env_id: str = "ALE/SpaceInvaders-v5"
    env_kwargs: dict[str, Any] = Field(default_factory=dict)
    seed: int = 42
    fps: int = 60
    max_episodes: int = 10


class AgentSettings(BaseModel):
    """Agent selection and model source settings.

    Attributes:
        kind: Action source kind used by runtime and tuning flows.
        sb3_repo_id: Default Hugging Face repository id for SB3 policies.
        sb3_filename: Default SB3 artifact filename.
        sb3_revision: Optional SB3 revision pin.
        sb3_algorithm: Optional explicit SB3 algorithm hint.
        device: Device string forwarded to SB3 loader.
        trusted_repo_prefixes: Trusted repository id prefixes.
        enforce_trusted_repo: Whether untrusted repo ids raise instead of warn.
    """

    kind: Literal["sb3", "random", "scripted"] = "sb3"
    sb3_repo_id: str = "sb3/ppo-SpaceInvadersNoFrameskip-v4"
    sb3_filename: str = "ppo-SpaceInvadersNoFrameskip-v4.zip"
    sb3_revision: str | None = "c0741d2e949614ef905e2489241c3032d1c9cce3"
    sb3_algorithm: Literal["a2c", "dqn", "ppo", "sac", "td3"] | None = None
    device: str = "cpu"
    trusted_repo_prefixes: list[str] = Field(default_factory=lambda: ["sb3/"])
    enforce_trusted_repo: bool = True


class VLMSettings(BaseModel):
    """Vision-language model server and sampling settings.

    Attributes:
        base_url: OpenAI-compatible endpoint base URL.
        model: Model identifier sent to the completion endpoint.
        max_tokens: Completion token cap per narration request.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        image_detail: Image detail hint for multimodal requests.
    """

    base_url: str = "http://localhost:8000/v1"
    model: str = "Qwen/Qwen3-VL-8B-Instruct-AWQ"
    max_tokens: int = 80
    temperature: float = 0.8
    top_p: float = 0.9
    image_detail: Literal["low", "high", "auto"] = "low"


class NarrationSettings(BaseModel):
    """Controls for narration trigger cadence and context.

    Attributes:
        interval_seconds: Baseline cadence interval for narration checks.
        min_gap_seconds: Cooldown between accepted narration candidates.
        reward_spike_threshold: Absolute reward trigger threshold.
        pixel_delta_threshold: Visual-delta trigger threshold.
        max_context_events: Number of recent events retained in prompt context.
        previous_narration_window: Number of previous narrations retained.
    """

    interval_seconds: float = 3.0
    min_gap_seconds: float = 1.5
    reward_spike_threshold: float = 5.0
    pixel_delta_threshold: float = 8.0
    max_context_events: int = 3
    previous_narration_window: int = 2


class KokoroSettings(BaseModel):
    """Kokoro voice and synthesis output settings.

    Attributes:
        voice: Kokoro voice id.
        speed: Voice speed multiplier.
        sample_rate: Output sample rate in Hz.
    """

    voice: str = "bm_george"
    speed: float = 0.95
    sample_rate: int = 24_000


class XTTSSettings(BaseModel):
    """Optional XTTS settings for alternate synthesis backends.

    Attributes:
        speaker_wav: Reference speaker WAV path.
    """

    speaker_wav: str = "data/voices/british_narrator.wav"


class TTSSettings(BaseModel):
    """Text-to-speech backend configuration.

    Attributes:
        enabled: Whether voice synthesis is enabled by default.
        engine: Active TTS backend name.
        kokoro: Kokoro backend settings.
        xtts: XTTS backend settings.
    """

    enabled: bool = True
    engine: Literal["kokoro", "xtts", "chatterbox"] = "kokoro"
    kokoro: KokoroSettings = Field(default_factory=KokoroSettings)
    xtts: XTTSSettings = Field(default_factory=XTTSSettings)


class DisplaySettings(BaseModel):
    """Window and subtitle rendering settings.

    Attributes:
        window_scale: Integer frame upscaling factor.
        min_window_width: Minimum window width in pixels.
        subtitle_font: Font family used for subtitle/HUD text.
        subtitle_size: Subtitle font size in pixels.
        subtitle_max_text_width: Maximum subtitle wrapping width in pixels.
        hud: Whether HUD text is enabled.
        text_bands: Whether HUD/subtitles use dedicated text bands.
    """

    window_scale: int = 3
    min_window_width: int = 960
    subtitle_font: str = "DejaVu Sans"
    subtitle_size: int = 22
    subtitle_max_text_width: int = 960
    hud: bool = True
    text_bands: bool = True


class RecordingSettings(BaseModel):
    """Optional recording output controls.

    Attributes:
        enabled: Whether session recording is enabled by default.
        out_path: Default recording output path.
    """

    enabled: bool = False
    out_path: str = "out/session.mp4"


class AppSettings(BaseSettings):
    """Top-level application settings model with layered source loading.

    Precedence is: explicit init kwargs, environment variables, dotenv values,
    then YAML defaults.

    Attributes:
        run: Runtime stepping defaults.
        agent: Action-source and policy-loading defaults.
        vlm: Narrator endpoint and sampling defaults.
        narration: Keyframe and context-window defaults.
        tts: Voice synthesis defaults.
        display: Display rendering defaults.
        recording: Recording defaults.
    """

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
        """Define source precedence for settings loading.

        Args:
            settings_cls: Effective settings subclass being instantiated.
            init_settings: Explicit init kwargs source.
            env_settings: Environment-variable source.
            dotenv_settings: Dotenv-file source.
            file_secret_settings: File-based secret source.

        Returns:
            Ordered tuple of settings sources used by pydantic-settings.
        """

        yaml_path = getattr(settings_cls, "_yaml_path", cls._yaml_path)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
            file_secret_settings,
        )


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppSettings:
    """Load app settings from YAML with environment-variable overrides.

    Args:
        config_path: YAML configuration file path.

    Returns:
        Validated application settings model.
    """

    yaml_path = Path(config_path)

    class SettingsWithYaml(AppSettings):
        _yaml_path: ClassVar[Path] = yaml_path

    return SettingsWithYaml()
