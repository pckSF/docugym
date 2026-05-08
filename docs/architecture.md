# Architecture

DocuGym has two primary integration paths:

- Canonical async runtime (`run_session` / `run_session_sync`) for CLI sessions.
- Synchronous Gym wrapper (`DocuWrapper`) for caller-driven step loops.

## Runtime Pipeline

The async runtime separates rendering, keyframe selection, narration generation,
TTS synthesis, and display updates into cooperating tasks.

```text
Env producer -> frame queue -> keyframe selector -> narration queue -> narrator
      |                               |                                |
      +-------------------------------+                                v
              display queue -------------------------------> subtitle queue
                                                                   |
                                                    optional TTS queue
                                                                   |
                                           optional audio output + recorder
```

Design goals:

- Keep gameplay smooth even when model latency spikes.
- Favor fresh narration over stale backlog.
- Decouple display refresh cadence from narration completion latency.

## Backpressure and Freshness

Queue behavior in runtime mode is bounded and freshness-biased:

- Frame queue: bounded (new frames can evict oldest stale frames).
- Narration candidate queue: bounded with drop-oldest semantics.
- TTS input queue: bounded with drop-oldest semantics.
- Subtitle queue: bounded, latest subtitle wins.

This prevents unbounded memory growth and avoids delayed narration that no
longer matches current gameplay context.

## Narration Triggering

Keyframe selection combines cadence and signal-based triggers:

- Baseline cadence from `narration.interval_seconds`.
- Minimum gap from `narration.min_gap_seconds`.
- Reward spikes above `narration.reward_spike_threshold`.
- Visual changes above `narration.pixel_delta_threshold`.
- Manual force trigger via runtime keyboard shortcut.

## Voice and Subtitle Model

Subtitle-only mode is the default. When voice is enabled:

- Runtime attempts to initialize the configured speaker/audio backend.
- If audio initialization fails, runtime falls back to subtitle-only mode.
- During active TTS playback, sentence-level outputs own subtitle updates so
  text tracks spoken output.

## Interactive Controls

Display actions supported during runtime:

- `space`: pause/resume stepping.
- `n`: force narration for the current frame.
- `m`: mute/unmute audio playback.
- `s`: save frame plus narration clip snapshot.

## Wrapper vs Runtime

Wrapper mode (`DocuWrapper`):

- Preserves Gym's `reset` and `step` semantics.
- Runs keyframe checks inline during `step`.
- Offloads narration/TTS work to a background thread.
- Injects diagnostics into `info["docugym"]`.

Runtime mode (`run_session`):

- Uses an end-to-end async pipeline.
- Handles agent action selection (`random`, `scripted`, `sb3`) internally.
- Includes optional recording and richer run-level metrics.

## Security and Trust Boundaries

SB3 model loading includes trust checks:

- Trusted prefixes are allowlisted in config.
- Untrusted repos require explicit CLI opt-in.
- Custom repos should be pinned by revision to reduce mutable-source risk.

## Extensibility Points

The runtime is protocol-oriented and supports custom components:

- Custom narrator clients (async or sync contract).
- Custom speaker clients.
- Custom audio output sinks.
- Custom recorder sinks.

See [API Reference](api_reference.md) and [Library Integration Guide](library_guide.md)
for signatures and expected behavior.
