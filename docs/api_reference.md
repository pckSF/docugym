# API Reference

This document summarizes stable, user-facing entrypoints for DocuGym.

## Python Package API

Import surface:

```python
from docugym import (
	AppSettings,
	DocuWrapper,
	NarrationContext,
	PromptTuningSample,
	RunResult,
	VLMNarrator,
	docuwrapper,
	get_system_prompt,
	load_settings,
	reset_system_prompt,
	run_prompt_tuning,
	run_session_sync,
	set_system_prompt,
)
```

The package root exposes the supported library surface for installed use:

- Wrapper API: `DocuWrapper`, `docuwrapper`, and callback type aliases.
- Configuration API: `AppSettings`, settings models, and `load_settings`.
- Narrator API: `VLMNarrator` and `NarrationContext`.
- Runtime API: `run_session_sync`, `run_session`, and `RunResult`.
- Tuning API: `run_prompt_tuning` and `PromptTuningSample`.
- Prompt API: `get_system_prompt`, `set_system_prompt`, and `reset_system_prompt`.

### docuwrapper

Factory alias that mirrors Gym wrapper construction style.

```python
docuwrapper(env, **kwargs) -> DocuWrapper
```

Use this when a calling framework expects a callable wrapper factory.

### DocuWrapper

Synchronous Gym wrapper that adds subtitles, narration, optional voice playback,
and display controls while preserving Gym `reset` and `step` semantics.

Common constructor parameters:

- `env_id`: optional override for context/log naming.
- `voice_enabled`: enable or disable spoken narration.
- `narration_interval_seconds`: baseline cadence trigger interval.
- `min_gap_seconds`: cooldown between accepted narration events.
- `reward_spike_threshold`: reward trigger sensitivity.
- `pixel_delta_threshold`: visual-delta trigger sensitivity.
- `on_narration`: callback `(text: str, step: int, latency_ms: float)`.
- `on_subtitle`: callback `(text: str)`.
- `on_audio_chunk`: callback `(chunk: np.ndarray)`.
- `on_status`: callback `(state: dict[str, Any])`.

Methods:

- `reset(seed=None, options=None) -> (observation, info)`
- `step(action) -> (observation, reward, terminated, truncated, info)`
- `state() -> dict[str, Any]`
- `close() -> None`

`info["docugym"]` payload keys:

- `step`
- `episode_reward`
- `narration_count`
- `dropped_narration_candidates`
- `last_latency_ms`
- `latest_narration`
- `latest_subtitle`
- `paused`
- `muted`
- `narrating`
- `window_open`
- `voice_enabled`

## CLI API

Main command group:

- `docugym show-config`
- `docugym list-voices`
- `docugym list-envs`
- `docugym smoketest`
- `docugym display-smoketest`
- `docugym run`

Tune command group:

- `docugym tune prompt`

Discover command options with:

```bash
docugym --help
docugym run --help
docugym tune prompt --help
```

`--config` accepts either an explicit YAML path or a packaged preset name. These
are equivalent from a source checkout:

```bash
docugym run --config atari
docugym run --config configs/atari.yaml
```

After installation, preset names such as `default`, `atari`, `lunarlander`, and
`carracing` work from any current directory.

## Configuration API

Load defaults or packaged presets:

```python
from docugym import load_settings

default_settings = load_settings()
atari_settings = load_settings("atari")
custom_settings = load_settings("configs/atari.yaml")
```

Environment variables with the `DOCUGYM_` prefix still override YAML values.

## Prompt Customization API

Use process-wide prompt helpers for interactive/library sessions:

```python
from docugym import get_system_prompt, reset_system_prompt, set_system_prompt

original_prompt = get_system_prompt()
set_system_prompt("Narrate with terse, analytical field notes.")
reset_system_prompt()
```

Use per-instance prompt overrides when a single narrator should differ from the
process default:

```python
from docugym import VLMNarrator

narrator = VLMNarrator(
	base_url="http://localhost:8000/v1",
	model="Qwen/Qwen3-VL-8B-Instruct-AWQ",
	max_tokens=80,
	temperature=0.8,
	top_p=0.9,
	system_prompt="Narrate with terse, analytical field notes.",
)
```

## Prompt Tuning Data Model

The prompt-tuning workflow returns a list of `PromptTuningSample` records with:

- `step`: sampled step index.
- `reward`: reward observed at sampling time.
- `narration`: generated narration text.
- `latency_ms`: end-to-end narration latency for that sample.

## Related References

- Configuration schema and defaults: `docs/config_reference.md`
- Documentation quality contract: `docs/documentation_contract.md`
- Architecture details and implementation stages: `specification.md`
