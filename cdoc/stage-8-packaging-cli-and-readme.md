---
type: decision
tags: [stage-8, cli, presets, readme, packaging]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-7-ui-polish-and-keyboard-controls.md, stage-9-mp4-recording.md]
---

# Stage 8 Packaging, CLI, and README

## Context

Stage 8 in specification.md requires a user-facing packaging pass over the existing
runtime: preset-driven CLI usage, discovery commands (`list-voices`, `list-envs`),
config presets in `configs/`, and a README quickstart/troubleshooting path suitable
for a fresh local setup.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: audit existing CLI/config/docs/test coverage for Stage 8 scope.
- Subtask 2: implement missing CLI commands and tests.
- Subtask 3: add preset config files for Atari, LunarLander, and CarRacing.
- Subtask 4: update README quickstart and troubleshooting.
- Subtask 5: validate with pre-commit and commit in logical blocks.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3 -> subtask 4 -> subtask 5.

## Research

### Existing project state before Stage 8 edits

- `docugym run --config ...` and direct override flags already existed.
- `--policy` shorthand and `--no-voice` subtitle-only mode already existed.
- `list-voices` and `list-envs` commands did not exist.
- `configs/` only contained `default.yaml`; no Stage 8 presets were present.
- README still documented a Stage 4 quickstart and lacked Stage 8 troubleshooting.

### Prior cdoc constraints considered

- `stage-7-ui-polish-and-keyboard-controls.md` preserves keyboard controls and text-band
  readability defaults; Stage 8 docs must describe those controls consistently.
- `stage-6-async-orchestration-and-keyframe-selection.md` defines stale-candidate
  dropping under backpressure; troubleshooting text should explain this expected behavior.

### External references consulted

- Typer command docs confirm `@app.command(...)` is the standard way to extend a
  multi-command CLI and that command registration order controls help ordering.
- Pydantic settings docs confirm environment values override defaults in BaseSettings;
  for preset listing this motivated parsing YAML into model defaults without pulling env
  overrides into displayed preset metadata.

### Implemented outcome summary

- Added `docugym list-voices` with Kokoro's eight British voices and sample lines.
- Added `docugym list-envs` that prints Stage 8 preset metadata from `configs/`.
- Added `configs/atari.yaml`, `configs/lunarlander.yaml`, and `configs/carracing.yaml`.
- Replaced Stage 4 README quickstart with Stage 8 preset workflow and troubleshooting.
- Added CLI tests covering the new listing commands.

### Assumptions

- confident: listing voices as identifiers plus sample narration lines satisfies the
  Stage 8 "voices + samples" requirement without requiring bundled audio files.
- likely: restricting `list-envs` to Stage 8 preset filenames keeps output stable and
  user-focused compared with enumerating all YAML files.
- likely: using `LunarLander-v2` in the preset is the safest default for available SB3
  checkpoint compatibility.
- uncertain: some users may prefer automatic preview audio for `list-voices`, which is
  intentionally out of scope for this stage.

## Options Considered

#### Option 1: Keep Stage 4 docs and add only missing commands
- **Description:** Add `list-voices`/`list-envs` but leave README and presets minimal.
- **Pros:** Lowest change surface and faster merge.
- **Cons:** Fails Stage 8 DoD expectations for quickstart/troubleshooting and presets.
- **Why ruled out:** Rejected because documentation and preset usability are core Stage 8
  deliverables, not optional extras.

#### Option 2: Implement full Stage 8 UX slice in place (chosen)
- **Description:** Add the two CLI discovery commands, ship three presets, expand README,
  and back changes with tests.
- **Pros:** Meets Stage 8 requirements while preserving established runtime architecture.
- **Cons:** Touches CLI, tests, docs, and config files in one stage.

#### Option 3: Introduce a new CLI sub-app/module split before Stage 8 features
- **Description:** Refactor command layout into multiple Typer modules first, then add
  Stage 8 functionality.
- **Pros:** Potentially cleaner long-term command organization.
- **Cons:** Adds architectural churn unrelated to Stage 8 user outcomes.
- **Why ruled out:** Rejected as premature restructuring with higher regression risk.

## Decision

Option 2 is selected.

It delivers Stage 8 directly by combining discovery commands, curated presets, and
onboarding docs without disrupting Stage 6/7 runtime behavior. Compared with Option 1,
it closes the user-facing gaps that prevented Stage 8 completion. Compared with Option 3,
it avoids unnecessary refactor risk while still adding test coverage.

## Pre-Mortem

- Failure mode: preset metadata diverges from real runtime defaults over time.
  - Mitigation in note: `list-envs` parses preset YAML through the current settings model.
- Failure mode: users copy an SB3 preset with env/version mismatch and get poor results.
  - Mitigation in note: README troubleshooting calls out SB3 version alignment.
- Failure mode: voice listing implies bundled audio previews that do not exist.
  - Mitigation in note: command wording uses sample lines, not playback claims.
- Failure mode: adding commands increases CLI surface without tests.
  - Mitigation in note: tests were added for both list commands.

## Changelog

- 2026-05-07: Created Stage 8 decision note with triage, research findings,
  decision rationale, and pre-mortem.
- 2026-05-07: Linked Stage 9 recording decision note for optional MP4 capture
  workflow and CLI/config integration.
