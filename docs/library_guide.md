# Library Integration Guide

DocuGym can be used as an installed Python library, not only via CLI.

## Public Import Surface

The package root exports:

- Config models: `AppSettings`, `RunSettings`, `AgentSettings`, `VLMSettings`,
  `NarrationSettings`, `TTSSettings`, `DisplaySettings`, `RecordingSettings`,
  `KokoroSettings`, `XTTSSettings`
- Config loader: `load_settings`
- Runtime API: `run_session`, `run_session_sync`, `RunResult`
- Wrapper API: `DocuWrapper`, `docuwrapper`
- Narrator API: `VLMNarrator`, `NarrationContext`
- Prompt API: `get_system_prompt`, `set_system_prompt`, `reset_system_prompt`,
  `DEFAULT_SYSTEM_PROMPT`
- Tuning API: `run_prompt_tuning`, `PromptTuningSample`

## Configuration-First Pattern

Load and override settings from presets or files:

```python
from docugym import load_settings

settings = load_settings("atari")
```

Environment variables with `DOCUGYM_` prefix override YAML values.

## Canonical Runtime API

Use the synchronous wrapper around the async runtime in non-async applications:

```python
from docugym import VLMNarrator, load_settings, run_session_sync

settings = load_settings("default")
narrator = VLMNarrator(
    base_url=settings.vlm.base_url,
    model=settings.vlm.model,
    max_tokens=settings.vlm.max_tokens,
    temperature=settings.vlm.temperature,
    top_p=settings.vlm.top_p,
    image_detail=settings.vlm.image_detail,
)

result = run_session_sync(
    env_id=settings.run.env_id,
    seed=settings.run.seed,
    fps=settings.run.fps,
    window_scale=settings.display.window_scale,
    subtitle_font=settings.display.subtitle_font,
    subtitle_size=settings.display.subtitle_size,
    subtitle_max_text_width=settings.display.subtitle_max_text_width,
    hud=settings.display.hud,
    text_bands=settings.display.text_bands,
    min_window_width=settings.display.min_window_width,
    env_kwargs=settings.run.env_kwargs,
    narrator=narrator,
    narration_interval_seconds=settings.narration.interval_seconds,
    min_gap_seconds=settings.narration.min_gap_seconds,
    reward_spike_threshold=settings.narration.reward_spike_threshold,
    pixel_delta_threshold=settings.narration.pixel_delta_threshold,
    max_context_events=settings.narration.max_context_events,
    previous_narration_window=settings.narration.previous_narration_window,
    agent_kind=settings.agent.kind,
    sb3_repo_id=settings.agent.sb3_repo_id,
    sb3_filename=settings.agent.sb3_filename,
    sb3_revision=settings.agent.sb3_revision,
)

print(result.narration_count, result.latency_p95_ms)
```

## Wrapper API

Use wrapper mode when your application already owns action selection and stepping.

```python
import gymnasium as gym

from docugym import DocuWrapper

env = gym.make("CartPole-v1", render_mode="rgb_array")
wrapped = DocuWrapper(env, env_id="CartPole-v1", voice_enabled=False)

obs, info = wrapped.reset(seed=42)
for _ in range(300):
    action = wrapped.action_space.sample()
    obs, reward, terminated, truncated, info = wrapped.step(action)
    state = info["docugym"]
    if terminated or truncated:
        obs, info = wrapped.reset()

wrapped.close()
```

## Wrapper Callback Hooks

`DocuWrapper` supports optional callbacks:

- `on_narration(text: str, step: int, latency_ms: float)`
- `on_subtitle(text: str)`
- `on_audio_chunk(chunk: numpy.ndarray)`
- `on_status(state: dict[str, Any])`

Use these hooks for telemetry, custom overlays, or external logging sinks.

## Prompt Customization

Set a process-wide default prompt:

```python
from docugym import reset_system_prompt, set_system_prompt

set_system_prompt("Narrate with concise tactical commentary.")
# Construct narrators or wrappers
reset_system_prompt()
```

Or pass a per-instance prompt to `VLMNarrator(system_prompt=...)`.

## Prompt Tuning Workflow

Collect comparable narration samples:

```python
from docugym import PromptTuningSample, VLMNarrator, run_prompt_tuning

narrator = VLMNarrator(
    base_url="http://localhost:8000/v1",
    model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
    max_tokens=80,
    temperature=0.8,
    top_p=0.9,
)

samples: list[PromptTuningSample] = run_prompt_tuning(
    env_id="ALE/SpaceInvaders-v5",
    seed=42,
    samples=10,
    step_stride=5,
    narrator=narrator,
    agent_kind="random",
    sb3_repo_id=None,
    sb3_filename=None,
    trusted_repo_prefixes=("sb3/",),
)
```

## Choosing Runtime vs Wrapper

Use runtime API when you want:

- End-to-end orchestration including agent actions.
- Optional recording and aggregate run metrics.
- Fewer integration responsibilities.

Use wrapper API when you want:

- Full control over the caller's stepping loop.
- Easy drop-in behavior in existing Gym pipelines.
- Step-level access to docugym state in `info` payloads.

For signatures and field-level details, see [API Reference](api_reference.md).
