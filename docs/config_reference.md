# Configuration Reference

This page documents the YAML and environment-variable configuration model used
by DocuGym.

## Loading and Precedence

Base loading precedence in `AppSettings`:

1. Explicit init kwargs.
2. Environment variables (`DOCUGYM_*`).
3. Dotenv values.
4. YAML config file values.
5. File-secret values.

CLI commands then layer command-line overrides on top of loaded settings for
run-specific behavior.

## Config Sources

`load_settings(config_path)` accepts:

- `None` or omitted: default preset.
- Packaged preset name: `default`, `atari`, `lunarlander`, `carracing`.
- Explicit YAML path.

Examples:

```python
from docugym import load_settings

default_settings = load_settings()
atari_settings = load_settings("atari")
path_settings = load_settings("configs/atari.yaml")
```

## Environment Variable Mapping

Environment variables use:

- Prefix: `DOCUGYM_`
- Nested delimiter: `__`

Examples:

- `DOCUGYM_RUN__FPS=75`
- `DOCUGYM_VLM__MODEL=Qwen/Qwen3-VL-4B-Instruct`
- `DOCUGYM_TTS__ENABLED=false`

## Top-Level Schema

Top-level sections:

- `run`
- `agent`
- `vlm`
- `narration`
- `tts`
- `display`
- `recording`

## run

- `env_id: str = "ALE/SpaceInvaders-v5"`
- `env_kwargs: dict[str, Any] = {}`
- `seed: int = 42`
- `fps: int = 60`
- `max_episodes: int = 10`

## agent

- `kind: "sb3" | "random" | "scripted" = "sb3"`
- `sb3_repo_id: str = "sb3/ppo-SpaceInvadersNoFrameskip-v4"`
- `sb3_filename: str = "ppo-SpaceInvadersNoFrameskip-v4.zip"`
- `sb3_revision: str | None = "c0741d2e949614ef905e2489241c3032d1c9cce3"`
- `sb3_algorithm: "a2c" | "dqn" | "ppo" | "sac" | "td3" | None = None`
- `device: str = "cpu"`
- `trusted_repo_prefixes: list[str] = ["sb3/"]`
- `enforce_trusted_repo: bool = true`

SB3 trust policy notes:

- Untrusted repositories require explicit CLI opt-in.
- Custom repository usage should pin `revision`.
- Mutable-head fetches are blocked when trust enforcement is active.

## vlm

- `base_url: str = "http://localhost:8000/v1"`
- `model: str = "Qwen/Qwen3-VL-8B-Instruct-AWQ"`
- `max_tokens: int = 80`
- `temperature: float = 0.8`
- `top_p: float = 0.9`
- `image_detail: "low" | "high" | "auto" = "low"`

## narration

- `interval_seconds: float = 3.0`
- `min_gap_seconds: float = 1.5`
- `reward_spike_threshold: float = 5.0`
- `pixel_delta_threshold: float = 8.0`
- `max_context_events: int = 3`
- `previous_narration_window: int = 2`
- `system_prompt: str | None = null`

## tts

- `enabled: bool = false`
- `engine: "kokoro" | "xtts" | "chatterbox" = "kokoro"`
- `kokoro.voice: str = "bm_george"`
- `kokoro.speed: float = 0.95`
- `kokoro.sample_rate: int = 24000`
- `xtts.speaker_wav: str = "data/voices/british_narrator.wav"`

Note: current runtime implementation supports Kokoro for active voice playback.

## display

- `window_scale: int = 3`
- `min_window_width: int = 960`
- `subtitle_font: str = "DejaVu Sans"`
- `subtitle_size: int = 22`
- `subtitle_max_text_width: int = 960`
- `hud: bool = true`
- `text_bands: bool = true`

## recording

- `enabled: bool = false`
- `out_path: str = "out/session.mp4"`

## Canonical Default YAML

```yaml
run:
  env_id: "ALE/SpaceInvaders-v5"
  env_kwargs:
    frameskip: 4
    repeat_action_probability: 0.25
    full_action_space: false
  seed: 42
  fps: 60
  max_episodes: 10

agent:
  kind: "sb3"
  sb3_repo_id: "sb3/ppo-SpaceInvadersNoFrameskip-v4"
  sb3_filename: "ppo-SpaceInvadersNoFrameskip-v4.zip"
  sb3_revision: "c0741d2e949614ef905e2489241c3032d1c9cce3"
  trusted_repo_prefixes: ["sb3/"]
  enforce_trusted_repo: true

vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"

narration:
  interval_seconds: 3.0
  min_gap_seconds: 1.5
  reward_spike_threshold: 5.0
  pixel_delta_threshold: 8.0
  max_context_events: 3
  previous_narration_window: 2

tts:
  enabled: false
  engine: "kokoro"
  kokoro:
    voice: "bm_george"
    speed: 0.95
    sample_rate: 24000
  xtts:
    speaker_wav: "data/voices/british_narrator.wav"

display:
  window_scale: 3
  min_window_width: 960
  subtitle_font: "DejaVu Sans"
  subtitle_size: 22
  subtitle_max_text_width: 960
  hud: true
  text_bands: true

recording:
  enabled: false
  out_path: "out/session.mp4"
```

## Minimal Random-Agent Example

```yaml
run:
  env_id: "CartPole-v1"
  fps: 60

agent:
  kind: "random"

vlm:
  base_url: "http://localhost:8000/v1"

narration:
  interval_seconds: 3.0

tts:
  enabled: false

display:
  window_scale: 2

recording:
  enabled: false
```

## CLI Interaction with Config

Important override behavior:

- `docugym run --voice` overrides `tts.enabled` for that run.
- `docugym run --record <path>` enables recording for that run.
- `--env-kwargs` JSON is merged on top of configured `run.env_kwargs`.
- `--narrate-every` converts frame cadence into interval-seconds using effective
  FPS.

## Preset Files

- `configs/default.yaml`
- `configs/atari.yaml`
- `configs/lunarlander.yaml`
- `configs/carracing.yaml`

## Related References

- [API Reference](api_reference.md)
- [CLI Reference](cli_reference.md)
- [Getting Started](getting_started.md)
