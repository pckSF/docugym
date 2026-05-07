---
type: decision
tags: [stage-9, recording, ffmpeg, runtime, cli]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-8-packaging-cli-and-readme.md]
---

# Stage 9 Optional MP4 Recording

## Context

Stage 9 in specification.md requires optional MP4 session recording with
ffmpeg, a `--record out/session.mp4` CLI path, and a practical fallback note for
users who prefer OBS capture.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: audit runtime, CLI, config, and tests for existing recording hooks.
- Subtask 2: choose recording architecture that preserves Stage 6 smoothness
  constraints and subtitle-only behavior.
- Subtask 3: implement runtime and CLI wiring with test coverage.
- Subtask 4: update README and cdoc index/links.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3 -> subtask 4.

## Research

### Current codebase state before Stage 9 edits

- Runtime had no MP4 capture path, but did already expose stable frame and audio
  touchpoints in Stage 6 (`display_task` frame presentation and `tts_task`
  chunk enqueue).
- Config already included `recording.enabled` and `recording.out_path`, but CLI
  did not expose a `--record` override and runtime ignored recording settings.
- Stage 7 included `s` shortcut snapshot saving, which is separate from session
  MP4 recording and should remain unchanged.

### Prior cdoc decisions that constrain this stage

- `stage-6-async-orchestration-and-keyframe-selection.md` requires non-blocking
  env stepping and stale-work dropping under load; recording must not introduce
  queue waits back into env stepping.
- `2026-04-27-voice-toggle-subtitle-only-mode.md` requires subtitle-only mode;
  recording should still work when voice output is disabled.
- `stage-8-packaging-cli-and-readme.md` established CLI ergonomics around
  config defaults with optional command-line overrides.

### External references consulted

- FFmpeg docs for rawvideo demuxing (`-f rawvideo`, `-pixel_format`,
  `-video_size`, `-framerate`) and PCM audio demuxing (`-f f32le`, `-ar`,
  `-ac`) to validate stream/mux command design.
- sounddevice callback guidance confirms callback path must stay lightweight and
  non-blocking; recording hooks therefore live outside the callback thread.

### Implemented outcome summary

- Added `docugym/recording.py` with `FFmpegSessionRecorder`:
  - Streams RGB frames to ffmpeg for H.264 video (`libx264`, `ultrafast`,
    `crf 20`).
  - Tees narration PCM chunks into a timestamp-aligned float32 mono stream with
    silence fill for gaps.
  - Finalizes to MP4 by muxing encoded video with AAC audio (`128k`).
- Extended Stage 6 runtime with optional recorder hooks:
  - Frame capture from display task.
  - Audio chunk tee from TTS task.
  - Graceful recorder finalization in shutdown path.
- Added CLI `--record` override and config fallback behavior:
  - `--record` path takes precedence.
  - Otherwise uses `recording.enabled` + `recording.out_path`.
- Added runtime and CLI tests covering recording wiring without requiring
  ffmpeg in test execution.
- Updated README with Stage 9 usage and OBS zero-code fallback note.

### Assumptions

- confident: hooking recording in display/TTS tasks (instead of env task or
  sounddevice callback) preserves Stage 6 non-blocking env constraints.
- confident: silence-filled PCM timeline is required to keep narration timing
  aligned to video duration.
- likely: two-pass local ffmpeg flow (video encode then mux) is easier to keep
  robust than dual live pipe multiplexing inside Python.
- uncertain: long-session AV drift under diverse host load still needs native
  manual verification beyond unit coverage.

## Options Considered

#### Option 1: OS loopback recording via sounddevice.InputStream
- **Description:** capture system output audio via loopback and mux with video.
- **Pros:** records exactly what the user hears.
- **Cons:** highly host-dependent device routing, brittle across Linux desktop
  stacks, and harder to test deterministically.
- **Why ruled out:** rejected for portability/reliability risk in default path.

#### Option 2: Tee synthesized PCM chunks and align by monotonic timestamps (chosen)
- **Description:** duplicate narration chunks in runtime, build an aligned PCM
  timeline with silence padding, and mux with captured frames.
- **Pros:** deterministic, testable in CI, and independent from host loopback
  configuration.
- **Cons:** reflects synthesized narration timeline, not full desktop mix.

#### Option 3: Write PNG/WAV intermediates and run ffmpeg offline once
- **Description:** store all frames and audio as files, then encode at shutdown.
- **Pros:** simple failure recovery and inspectable artifacts.
- **Cons:** large temporary storage footprint and unnecessary I/O overhead.
- **Why ruled out:** rejected due storage/performance cost for longer sessions.

## Decision

Option 2 is selected.

It best balances runtime safety, portability, and testability while matching the
Stage 9 requirement for ffmpeg-based MP4 output. Compared with Option 1, it
avoids host loopback fragility. Compared with Option 3, it avoids oversized frame
intermediates while still producing a predictable muxed output.

## Pre-Mortem

- Failure mode: `ffmpeg` missing from PATH causes recording startup failures.
  - Mitigation in note: fail early with explicit runtime error; README now calls
    out ffmpeg dependency and the no-record fallback.
- Failure mode: recorder write failure mid-run (broken pipe / codec failure).
  - Mitigation in note: runtime logs warning and disables recording while keeping
    gameplay/narration running.
- Failure mode: sparse narration creates compressed audio timeline drift.
  - Mitigation in note: recorder pads silence based on monotonic timestamps and
    session end time before muxing.
- Failure mode: subtitle-only mode breaks recording assumptions.
  - Mitigation in note: recorder still captures video and writes a valid silent
    or sparse-audio track when voice is disabled.

## Changelog

- 2026-05-07: Created Stage 9 decision note documenting ffmpeg-based recording
  architecture, tradeoffs, and risk mitigations.
