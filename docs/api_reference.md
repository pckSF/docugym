# API Reference

This reference captures the stable, user-facing Python and CLI surface of
DocuGym.

## Package Exports

Public root imports from `docugym`:

```python
from docugym import (
	AgentSettings,
	AppSettings,
	AudioChunkCallback,
	DEFAULT_SYSTEM_PROMPT,
	DisplaySettings,
	DocuWrapper,
	KokoroSettings,
	NarrationCallback,
	NarrationContext,
	NarrationSettings,
	PromptTuningSample,
	RecordingSettings,
	RunResult,
	RunSettings,
	StatusCallback,
	SubtitleCallback,
	TTSSettings,
	VLMNarrator,
	VLMSettings,
	XTTSSettings,
	docuwrapper,
	get_system_prompt,
	load_settings,
	reset_system_prompt,
	run_prompt_tuning,
	run_session,
	run_session_sync,
	set_system_prompt,
)
```

## Runtime API

## run_session

Asynchronous canonical session runner.

```python
async def run_session(..., on_narration: Callable[[str, int, float], None] | None = None) -> RunResult
```

Use this in async applications that want full control of event loop ownership.

Major parameter groups:

- Environment and pacing: `env_id`, `seed`, `fps`, `env_kwargs`, `max_steps`,
  `max_episodes`
- Display: `window_scale`, `subtitle_font`, `subtitle_size`,
  `subtitle_max_text_width`, `hud`, `text_bands`, `min_window_width`
- Narration triggers: `narration_interval_seconds`, `min_gap_seconds`,
  `reward_spike_threshold`, `pixel_delta_threshold`, `max_context_events`,
  `previous_narration_window`
- Agent and policy: `agent_kind`, `sb3_repo_id`, `sb3_filename`,
  `sb3_revision`, `sb3_algorithm`, `sb3_device`,
  `trusted_repo_prefixes`, `enforce_trusted_repo`
- Voice and audio: `voice_enabled`, `tts_engine`, `tts_voice`, `tts_speed`,
  `tts_sample_rate`, `speaker`, `audio_output`
- Recording: `record_out_path`, `recorder`, `ffmpeg_binary`
- Observability: `on_narration`

## run_session_sync

Synchronous wrapper around `run_session`.

```python
def run_session_sync(**kwargs: Any) -> RunResult
```

Use this from CLI tools, scripts, or synchronous applications. It raises
`RuntimeError` if called inside an already-running event loop.

## RunResult

Session metrics dataclass returned by runtime APIs.

Fields:

- `rendered_steps: int`
- `narration_count: int`
- `latency_p50_ms: float | None`
- `latency_p95_ms: float | None`
- `dropped_narration_candidates: int`
- `dropped_keyframe_candidates: int`
- `dropped_tts_inputs: int`
- `narration_failures: int`
- `recording_failed: bool`

## Wrapper API

## DocuWrapper

Gym wrapper for caller-owned step loops.

```python
class DocuWrapper(gym.Wrapper):
	def reset(seed: int | None = None, options: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]
	def step(action: Any) -> tuple[Any, float, bool, bool, dict[str, Any]]
	def state() -> dict[str, Any]
	def close() -> None
```

Notable constructor options:

- Display and layout: `fps`, `window_scale`, `min_window_width`, `hud`,
  `text_bands`, `subtitle_font`, `subtitle_size`, `subtitle_max_text_width`
- Narrator transport/model: `base_url`, `model`, `max_tokens`, `temperature`,
  `top_p`, `image_detail`, `system_prompt`, or injected `narrator`
- Narration policy: `narration_interval_seconds`, `min_gap_seconds`,
  `reward_spike_threshold`, `pixel_delta_threshold`, `max_context_events`,
  `previous_narration_window`
- Voice: `voice_enabled`, `tts_engine`, `tts_voice`, `tts_speed`,
  `tts_sample_rate`, optional injected `speaker` and `audio_output`
- Callbacks: `on_narration`, `on_subtitle`, `on_audio_chunk`, `on_status`

`info["docugym"]` contains live wrapper diagnostics, including counters,
latency, latest narration/subtitle text, pause/mute flags, and window state.

## docuwrapper

Callable factory alias for integration points that expect a plain wrapper
constructor function.

```python
def docuwrapper(env: gym.Env[Any, Any], **kwargs: Any) -> DocuWrapper
```

## Callback Type Aliases

- `NarrationCallback = Callable[[str, int, float], None]`
- `SubtitleCallback = Callable[[str], None]`
- `AudioChunkCallback = Callable[[numpy.ndarray], None]`
- `StatusCallback = Callable[[dict[str, Any]], None]`

## Narrator API

## NarrationContext

Lightweight context object passed into narration requests.

Fields:

- `env_human_name: str`
- `previous_narration: str = ""`
- `event_summary: str = ""`

## VLMNarrator

OpenAI-compatible multimodal narrator client.

Primary methods:

- `await narrate_frame(frame: numpy.ndarray, context: NarrationContext) -> str`
- `narrate_frame_sync(frame: numpy.ndarray, context: NarrationContext) -> str`
- `await wait_until_ready(timeout_seconds=60.0, poll_interval_seconds=1.0) -> bool`
- `wait_until_ready_sync(timeout_seconds=60.0, poll_interval_seconds=1.0) -> bool`
- `await aclose() -> None`

Constructor highlights:

- endpoint/model: `base_url`, `model`
- sampling: `max_tokens`, `temperature`, `top_p`, `image_detail`
- transport: `timeout_seconds`, `readiness_timeout_seconds`
- prompt: optional `system_prompt`

## Prompt and Tuning API

## Prompt helpers

- `get_system_prompt() -> str`
- `set_system_prompt(prompt: str) -> None`
- `reset_system_prompt() -> None`
- `DEFAULT_SYSTEM_PROMPT: str`

## run_prompt_tuning

Collects fixed-stride narrated samples for prompt/model comparisons.

```python
def run_prompt_tuning(..., samples: int, step_stride: int, narrator: SyncNarrator, ...) -> list[PromptTuningSample]
```

## PromptTuningSample

Dataclass fields:

- `step: int`
- `reward: float`
- `narration: str`
- `latency_ms: float`

## CLI Surface

The installed script entrypoint is:

```bash
docugym
```

Commands:

- `show-config`
- `list-voices`
- `list-envs`
- `smoketest`
- `display-smoketest`
- `run`
- `tune prompt`

See [CLI Reference](cli_reference.md) for options and examples.

## Related References

- [Configuration Reference](config_reference.md)
- [Library Integration Guide](library_guide.md)
- [Architecture](architecture.md)
