---
type: decision
tags: [narration, tts, subtitles, performance, testing, stage-5]
created: 2026-04-27
updated: 2026-04-27
status: active
related: [stage-4-vlm-narration-sync.md, stage-3-display-layer.md]
---

# 2026-04-27 Voice Toggle and Subtitle-Only Mode

## Context

The project currently treats voiced narration as the default experience, but
there are valid runtime contexts where audio narration should be optional while
subtitle narration remains available.

## Research

The design should explicitly support a runtime flag that enables or disables
voiced output while preserving generated narration text and subtitle display.
This change is needed for three reasons:

- Some sessions should be silent by choice, where users prefer reading subtitles
  without speech output.
- Subtitle-only mode is less computationally demanding and better suited for
  weaker systems or times when GPU/CPU resources are constrained.
- A dedicated no-voice mode allows cleaner separation of build and test flows,
  so frame-to-text narration can be validated independently from TTS/audio.

### Assumptions

- `confident`: Narration text generation remains valuable even when TTS is
  disabled.
- `likely`: A simple boolean flag (`--voice/--no-voice` and config mirror) is
  sufficient for first implementation.
- `likely`: Keeping subtitles enabled in both modes avoids user-facing feature
  loss when voice is disabled.
- `uncertain`: Exact performance gains will vary by system and model mix.

## Options Considered

#### Option 1: Keep voice always on
- **Description:** Require TTS/audio pipeline in all narration runs.
- **Pros:** Simplest conceptual user story.
- **Cons:** Reduces flexibility, increases compute requirements, and couples
  unrelated test paths.
- **Why ruled out:** Does not support silent usage or low-resource workflows.

#### Option 2: Add explicit voice toggle flag (chosen)
- **Description:** Add runtime and config toggles for voiced narration while
  keeping subtitles active.
- **Pros:** Flexible UX, lower-resource mode, and better test/build separation.
- **Cons:** Adds one control path to test in CLI/runtime.

#### Option 3: Maintain separate voice and no-voice executables
- **Description:** Split pipeline into two commands/binaries.
- **Pros:** Hard separation of concerns.
- **Cons:** Duplicates run-path surface and increases maintenance burden.
- **Why ruled out:** Overly heavy for the current project size.

## Decision

Option 2 is selected.

The architecture should preserve text narration as the core output and treat
voice as a toggleable rendering channel. The expected interface is a runtime
flag (for example `--voice/--no-voice`) with a matching config field (for
example `tts.enabled`) defaulting to enabled.

## Changelog

- 2026-04-27: Created decision note requiring toggleable voice output with
  subtitle-only operation for silent use, lower-resource runs, and decoupled
  testing/build flow.
