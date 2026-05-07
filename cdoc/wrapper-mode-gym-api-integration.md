---
type: decision
tags: [wrapper, gymnasium, runtime, narration, subtitles]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-6-async-orchestration-and-keyframe-selection.md, stage-7-ui-polish-and-keyboard-controls.md, stage-8-packaging-cli-and-readme.md, final-setup-runtime-and-naming-consolidation.md]
---

# Wrapper Mode Gym API Integration

## Context

The project had a production-ready CLI runtime (`docugym run`) but no direct API for
wrapping an already-created Gymnasium environment in user-defined loops. The requested
capability is a `docuwrapper(env, ...)` path that preserves normal environment usage while
adding live DocuGym narration/subtitles and command-like toggles as constructor options.

## Research

- Existing runtime and cdoc decisions establish the canonical async pipeline and keyboard
  controls in `run_session`, but that path expects ownership of env stepping.
- Existing display and subtitle behavior already supports pause, force-narrate, mute,
  and save-clip actions, which can be reused in wrapper mode.
- Existing narrator and Kokoro integrations are reusable in wrapper mode through their
  sync wrappers, avoiding event-loop coupling for caller code.

### Implemented Phase 1 Outcome

- Added `docugym/wrapper.py` with `DocuWrapper` and `docuwrapper(env, ...)`.
- Preserved Gym-style `reset`/`step` signatures and injected wrapper telemetry into
  `info["docugym"]`.
- Added always-on wrapper display behavior with subtitles and keyboard shortcuts.
- Added optional callback hooks (`on_narration`, `on_subtitle`, `on_audio_chunk`,
  `on_status`) for experimental integration.
- Exported wrapper API from package root and documented wrapper usage in README.
- Added focused wrapper tests validating metadata emission, callback wiring,
  force-narrate, and pause hold/release behavior.

### Implemented Phase 2 Outcome

- Extracted shared keyframe trigger/cooldown logic into `docugym/keyframes.py`
  (`KeyframeSelector`, `KeyframeDecision`, `mean_abs_pixel_delta`).
- Updated `docugym/runtime.py` keyframe task to consume shared selector logic,
  preserving stale-candidate drop policy and enqueue-on-success cooldown updates.
- Updated `docugym/wrapper.py` to use the same selector in wrapper mode,
  reducing drift risk between wrapper and CLI narration trigger behavior.
- Added `tests/test_keyframes.py` to lock cadence/reward/delta trigger semantics
  and cooldown behavior independent of runtime orchestration details.

### Implemented Phase 3 Outcome

- Extracted shared narration event/context formatting helpers into
  `docugym/narration_events.py` (`format_event_summary`, `humanize_env_id`,
  `join_recent_events`, `join_previous_narrations`).
- Updated `docugym/runtime.py` and `docugym/wrapper.py` to consume shared
  formatting/context helpers, reducing prompt-context drift between production
  and wrapper paths.
- Added `tests/test_narration_events.py` to lock event-summary formatting and
  context-join behavior.

## Options Considered

#### Option 1: Keep CLI-only production surface
- **Description:** Do not add wrapper API; require all narrated runs to use CLI.
- **Pros:** Single runtime entrypoint and lower API surface.
- **Cons:** Prevents direct integration into training loops and experimentation code.
- **Why ruled out:** Rejected because the requested workflow requires in-process env wrapping.

#### Option 2: Add Gym-compatible wrapper with local background narration worker (chosen)
- **Description:** Add `docuwrapper(env, ...)` that delegates env interaction and manages
  narration/subtitle/voice components in wrapper-owned state.
- **Pros:** Immediate experimental usability without changing CLI production flow.
- **Cons:** Introduces partial orchestration duplication versus the canonical runtime.

#### Option 3: Refactor runtime first, then add wrapper
- **Description:** Delay wrapper until a shared orchestration core is extracted.
- **Pros:** Cleaner architecture before exposing new API.
- **Cons:** Delays user-facing wrapper capability and increases implementation latency.
- **Why ruled out:** Rejected for phase ordering; wrapper delivery was prioritized first,
  with shared-core extraction planned as follow-on work.

## Decision

Option 2 is selected for Phase 1 delivery.

This delivers a usable wrapper API immediately while preserving the existing CLI as the
recommended production path for recording and full run management.

## Pre-Mortem

- Failure mode: wrapper orchestration drifts from canonical runtime behavior.
  - Mitigation in note: Phase 2 extracts and reuses shared orchestration primitives.
- Failure mode: callback failures break training loops.
  - Mitigation in note: callback execution is guarded and non-fatal.
- Failure mode: pause behavior conflicts with caller step loops.
  - Mitigation in note: wrapper pause intentionally blocks progression until unpaused,
    matching requested behavior.

## Changelog

- 2026-05-07: Created decision note for Phase 1 `docuwrapper(env, ...)` implementation,
  tests, and README documentation.
- 2026-05-07: Updated for Phase 2 refactor that shares keyframe selection logic
  between wrapper and canonical runtime paths.
- 2026-05-07: Updated for Phase 3 refactor that shares narration-event formatting
  and context-string assembly between wrapper and canonical runtime paths.
