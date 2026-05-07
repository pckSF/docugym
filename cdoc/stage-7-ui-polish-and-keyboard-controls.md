---
type: decision
tags: [stage-7, display, runtime, shortcuts, subtitles, hud]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-6-async-orchestration-and-keyframe-selection.md, stage-3-display-layer.md, stage-3-display-min-width-and-subtitle-width-policy.md, 2026-04-27-voice-toggle-subtitle-only-mode.md, stage-5-local-tts-streaming-audio.md, stage-8-packaging-cli-and-readme.md]
---

# Stage 7 UI Polish and Keyboard Controls

## Context

Stage 7 in specification.md asks for subtitle-card polish, a richer HUD, and runtime
keyboard controls (`space`, `n`, `m`, `s`). Existing cdoc decisions already moved subtitle
and HUD text away from pixel overlays into dedicated text bands for readability.
This implementation must preserve that non-overlay policy while adding Stage 7 controls.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: re-read Stage 3/5/6 display and voice-toggle decisions to identify
  constraints before code edits.
- Subtask 2: implement display input plumbing and HUD state indicators without
  regressing text-band readability behavior.
- Subtask 3: wire keyboard actions into Stage 6 async orchestration with bounded
  queues and no env-loop blocking.
- Subtask 4: add tests for shortcut behavior and re-run lint/test gates.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3 -> subtask 4.

## Research

### Existing constraints from prior cdoc decisions

- `stage-3-display-layer.md` established the PyGame display abstraction and HUD/subtitle
  rendering responsibilities.
- `2026-04-24-stage-3-display-follow-up-validation-and-text-bands.md` and
  `stage-3-display-min-width-and-subtitle-width-policy.md` established that readable,
  non-overlay text bands are preferred over drawing text directly on gameplay pixels.
- `2026-04-27-voice-toggle-subtitle-only-mode.md` and `stage-5-local-tts-streaming-audio.md`
  require voice to remain optional while subtitles stay active.
- `stage-6-async-orchestration-and-keyframe-selection.md` requires stale work dropping and
  non-blocking env stepping, so keyboard-triggered narration must honor queue pressure policy.

### Codebase findings before Stage 7 edits

- Display already supported text-band mode and minimum-width layout, but keyboard handling only
  supported `Escape` for close.
- HUD showed env/step/reward only; no runtime state indicators.
- Stage 6 runtime had no pause/force-narrate/mute/save action handling.
- No clip snapshot path existed for saving current frame plus narration text.

### Implemented outcome

- Added keyboard action mapping in display (`space`, `n`, `m`, `s`) with action polling API.
- Added HUD runtime indicators: narration activity, paused/running state, and muted/audible state.
- Added Stage 6 action handling:
  - `space`: toggles env stepping pause without closing display.
  - `n`: pushes a manual narration candidate into the bounded narration queue.
  - `m`: toggles mute state, flushes pending TTS queue/audio buffer when muting.
  - `s`: saves current frame PNG + last narration text to `out/clips/`.
- Added audio output `clear()` support for immediate mute responsiveness.
- Added tests for shortcut mapping, HUD status text, forced narration, mute behavior,
  and clip-save action routing.
- Verification: `uv run ruff check .` and `uv run pytest -q` both pass.

### Assumptions

- confident: preserving text bands as the default subtitle/HUD presentation better matches
  prior readability decisions than reintroducing overlay-first behavior.
- confident: manual `force_narrate` should use the same bounded queue/drop policy as automatic
  keyframe candidates to avoid stale commentary buildup.
- likely: muting by gating new TTS work and clearing queued/buffered audio yields a practical
  UX without adding complex cancellation to synthesis internals.
- uncertain: very high-frequency user input (rapid shortcut spamming) may still need additional
  debouncing if seen in longer manual sessions.

## Options Considered

#### Option 1: Stage 7 subtitle overlay card and controls in display only
- **Description:** Reintroduce overlay card rendering as the primary subtitle mode and keep most shortcut effects local to display.
- **Pros:** Directly mirrors Stage 7 wording and keeps runtime edits small.
- **Cons:** Conflicts with established non-overlay readability decisions and cannot safely implement pause/narration/audio control without runtime coupling.
- **Why ruled out:** Rejected due readability-policy conflict and insufficient control-plane reach.

#### Option 2: Keep text bands and add runtime-backed shortcut control plane (chosen)
- **Description:** Preserve text-band layout, expose display keyboard intents, and apply pause/force/mute/save effects in Stage 6 runtime tasks.
- **Pros:** Aligns with readability decisions, keeps env loop non-blocking, and centralizes behavior where narration/TTS queues already exist.
- **Cons:** Adds cross-task state and a modest increase in runtime complexity.

#### Option 3: Split controls into a separate process or thread controller
- **Description:** Route keyboard actions through an external controller to orchestrate runtime state.
- **Pros:** Strong separation of concerns.
- **Cons:** Added IPC complexity and testing burden for limited stage scope.
- **Why ruled out:** Rejected as unnecessary architecture expansion for current requirements.

## Decision

Option 2 is selected.

It preserves the readability advantages from Stage 3 follow-up decisions while adding Stage 7
controls where they can be applied safely against existing queues and worker tasks. Compared
with Option 1, it avoids reversing the no-overlay policy. Compared with Option 3, it delivers
required behavior with lower complexity and better testability inside current architecture.

## Pre-Mortem

- Failure mode: pause state could stall progression if users do not realize playback is paused.
  - Mitigation in note: explicit HUD paused/running indicator.
- Failure mode: force-narrate spam could crowd normal candidates.
  - Mitigation in note: forced candidates still use bounded queue with drop-oldest behavior.
- Failure mode: mute toggle feels delayed due queued audio.
  - Mitigation in note: clear TTS queue and audio buffer immediately when muting.
- Failure mode: clip snapshots fail on hosts without Pillow.
  - Mitigation in note: save path failures are logged and do not crash runtime loop.

## Changelog

- 2026-05-07: Created Stage 7 decision note covering keyboard controls, HUD state indicators,
  text-band subtitle policy continuity, and runtime integration tradeoffs.
- 2026-05-07: Linked Stage 8 packaging/CLI/readme decision note.
