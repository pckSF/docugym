# API Reference

This document summarizes stable, user-facing entrypoints for DocuGym.

## Python Package API

Import surface:

```python
from docugym import DocuWrapper, docuwrapper
```

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
