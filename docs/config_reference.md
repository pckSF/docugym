# Configuration Reference

This document describes the YAML and environment-variable configuration surface
used by DocuGym.

## Source Precedence

Base precedence in `AppSettings`:

1. Explicit init values.
2. Environment variables (`DOCUGYM_*`).
3. Dotenv values.
4. YAML file values.
5. File secrets.

CLI commands may additionally apply command-line overrides on top of loaded
settings for specific run/session options.

## Environment Variable Mapping

Environment variables use:

- Prefix: `DOCUGYM_`
- Nested delimiter: `__`

Examples:

- `DOCUGYM_RUN__FPS=75`
- `DOCUGYM_VLM__MODEL=Qwen/Qwen3-VL-4B-Instruct`
- `DOCUGYM_TTS__ENABLED=false`

## Top-Level Schema

### run

- `env_id` (`str`, default `ALE/SpaceInvaders-v5`)
- `env_kwargs` (`dict[str, Any]`, default `{}`)
- `seed` (`int`, default `42`)
- `fps` (`int`, default `60`)
- `max_episodes` (`int`, default `10`)

### agent

- `kind` (`sb3 | random | scripted`, default `sb3`)
- `sb3_repo_id` (`str`, default `sb3/ppo-SpaceInvadersNoFrameskip-v4`)
- `sb3_filename` (`str`, default `ppo-SpaceInvadersNoFrameskip-v4.zip`)
- `sb3_revision` (`str | null`, default pinned commit)
- `sb3_algorithm` (`a2c | dqn | ppo | sac | td3 | null`, default `null`)
- `device` (`str`, default `cpu`)
- `trusted_repo_prefixes` (`list[str]`, default `["sb3/"]`)
- `enforce_trusted_repo` (`bool`, default `true`)

### vlm

- `base_url` (`str`, default `http://localhost:8000/v1`)
- `model` (`str`, default `Qwen/Qwen3-VL-8B-Instruct-AWQ`)
- `max_tokens` (`int`, default `80`)
- `temperature` (`float`, default `0.8`)
- `top_p` (`float`, default `0.9`)
- `image_detail` (`low | high | auto`, default `low`)

### narration

- `interval_seconds` (`float`, default `3.0`)
- `min_gap_seconds` (`float`, default `1.5`)
- `reward_spike_threshold` (`float`, default `5.0`)
- `pixel_delta_threshold` (`float`, default `8.0`)
- `max_context_events` (`int`, default `3`)
- `previous_narration_window` (`int`, default `2`)

### tts

- `enabled` (`bool`, default `false`)
- `engine` (`kokoro | xtts | chatterbox`, default `kokoro`)
- `kokoro.voice` (`str`, default `bm_george`)
- `kokoro.speed` (`float`, default `0.95`)
- `kokoro.sample_rate` (`int`, default `24000`)
- `xtts.speaker_wav` (`str`, default `data/voices/british_narrator.wav`)

### display

- `window_scale` (`int`, default `3`)
- `min_window_width` (`int`, default `960`)
- `subtitle_font` (`str`, default `DejaVu Sans`)
- `subtitle_size` (`int`, default `22`)
- `subtitle_max_text_width` (`int`, default `960`)
- `hud` (`bool`, default `true`)
- `text_bands` (`bool`, default `true`)

### recording

- `enabled` (`bool`, default `false`)
- `out_path` (`str`, default `out/session.mp4`)

## Minimal Example

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

## Preset Files

Packaged presets live under `configs/`:

- `configs/default.yaml`
- `configs/atari.yaml`
- `configs/lunarlander.yaml`
- `configs/carracing.yaml`

## Related References

- API reference: `docs/api_reference.md`
- Documentation quality policy: `docs/documentation_contract.md`
