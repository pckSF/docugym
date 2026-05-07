---
type: decision
tags: [stage-6, runtime, asyncio, keyframes, narration, backpressure]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-5-local-tts-streaming-audio.md, stage-4-vlm-narration-sync.md, 2026-04-27-voice-toggle-subtitle-only-mode.md, stage-7-ui-polish-and-keyboard-controls.md]
---

# Stage 6 Async Orchestration and Keyframe Selection

## Context

With Stage 5 complete, the runtime still used a synchronous gameplay loop where
narration and TTS could stall frame stepping. Stage 6 requires a true asyncio
pipeline with bounded queues, keyframe heuristics, and explicit backpressure so
gameplay stays smooth while narration can lag slightly and drop stale work.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: verify existing runtime architecture and identify Stage 6 gaps.
- Subtask 2: implement async task pipeline (env, keyframe selector, VLM, TTS,
  audio callback bridge, display loop).
- Subtask 3: update CLI wiring and tests for Stage 6 behavior.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3.

## Research

### Codebase state before this change

- `docugym/runtime.py` centered on `run_stage4_session`, a single synchronous
  loop with fixed `narrate_every` cadence.
- `docugym/audio.py` already provided a queue-fed sounddevice callback with
  drop-oldest behavior under queue pressure.
- `docugym/tts.py` already exposed async `speak(...)` and sync `speak_sync(...)`.
- `docugym/narrator.py` already exposed async `narrate_frame(...)` and sync
  wrapper methods.
- `docugym/cli.py` `run` command still called `run_stage4_session`.

### Stage 6 gaps identified

- Missing frame queue decoupling from env stepping.
- Missing keyframe selector heuristics (cadence + reward spike + episode
  boundary + visual delta + cooldown).
- Missing bounded async narrator/TTS workers with explicit candidate dropping.
- Missing runtime metric for dropped stale narration work.

### Implemented outcome

- Added `run_stage6_session` (async) and `run_stage6_session_sync` wrapper.
- Implemented Task A-F pipeline with bounded queues and semaphores:
  - env producer -> frame queue (maxsize 4, drop-oldest)
  - keyframe selector -> narration candidate queue
  - narrator worker (concurrency 1)
  - TTS worker (concurrency 1)
  - audio callback sink via existing `AudioOutput`
  - display worker consuming latest frame/subtitle state
- Added keyframe heuristics using configured thresholds and cooldown.
- Added explicit logging/counter for dropped stale narration candidates and
  dropped queued TTS narration text.
- Updated CLI `run` to call Stage 6 runtime and map optional
  `--narrate-every` override to `narration_interval_seconds`.
- Added tests for Stage 6 reward-spike narration triggering and backpressure
  dropping behavior; updated CLI tests for Stage 6 runtime wiring.

### Assumptions

- confident: preserving `run_stage4_session` while routing CLI `run` to Stage 6
  reduces regression risk and keeps a compatibility path.
- confident: dropping oldest queued narration candidates is preferable to
  speaking stale commentary late.
- likely: visual-delta mean absolute pixel difference is sufficient as a cheap
  first keyframe heuristic.
- likely: one narrator worker and one TTS worker are the right GPU/CPU bounds
  for single-card local deployment.
- uncertain: long-session behavior under real GPU load may need threshold tuning
  beyond unit-test coverage.

## Options Considered

#### Option 1: Keep synchronous loop and add only more trigger rules
- **Description:** Extend Stage 4 loop with reward/pixel heuristics but keep all
  narration and TTS calls inline.
- **Pros:** Small code diff and easy to reason about.
- **Cons:** Does not satisfy Stage 6 non-blocking architecture goals; gameplay
  still stalls under narration/TTS latency.
- **Why ruled out:** Rejected because it fails the primary Stage 6 requirement
  that the env loop must not block on inference.

#### Option 2: Full asyncio queue pipeline with bounded workers (chosen)
- **Description:** Implement separate async tasks for env stepping, keyframe
  selection, narration, TTS, and display with bounded queues and drop policies.
- **Pros:** Satisfies Stage 6 architecture, isolates bottlenecks, and supports
  stale-work dropping under load.
- **Cons:** Higher implementation complexity and more coordination state.

#### Option 3: Multi-process redesign for every pipeline stage
- **Description:** Split env, display, narrator, and TTS into separate processes
  with IPC queues.
- **Pros:** Strong isolation and potentially better CPU scheduling control.
- **Cons:** Significant complexity and operational overhead beyond current stage
  scope.
- **Why ruled out:** Rejected as over-engineering for current requirements and
  existing single-process architecture.

## Decision

Option 2 is selected.

This approach directly addresses Stage 6 requirements while reusing stable Stage
4/5 components (`VLMNarrator`, `KokoroTTS`, `AudioOutput`, `Display`). Compared
with Option 1, it removes inference blocking from the env producer path.
Compared with Option 3, it delivers required decoupling without introducing IPC
and process-lifecycle complexity.

## Pre-Mortem

- Failure mode: keyframe heuristics over-trigger and flood narrator queue.
  - Mitigation in note: bounded queue with drop-oldest and explicit dropped-work
    metrics for tuning.
- Failure mode: subtitle flow drifts from spoken sentence timing in stressed
  runs.
  - Mitigation in note: TTS worker emits per-sentence subtitle updates and
    bypasses audio fully in subtitle-only mode.
- Failure mode: window close during synthesis leaves workers hanging.
  - Mitigation in note: shared stop event, queue-drain exit conditions, and
    task cancellation in runtime shutdown path.
- Failure mode: Stage 6 cadence override confuses existing users.
  - Mitigation in note: keep `--narrate-every` as optional override and default
    to `narration.interval_seconds` config.

## Changelog

- 2026-05-07: Created Stage 6 decision note documenting async orchestration,
  keyframe selection heuristics, backpressure policy, CLI wiring, and tests.
- 2026-05-07: Linked Stage 7 UI and keyboard-controls decision note.
