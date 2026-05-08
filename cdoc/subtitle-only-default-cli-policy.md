---
type: decision
tags: [narration, tts, defaults, cli, performance]
created: 2026-05-08
updated: 2026-05-08
status: active
related: [2026-04-27-voice-toggle-subtitle-only-mode.md, 2026-05-08-documentation-governance-and-reference-uplift.md]
---
# Subtitle-Only Default for CLI Runs

## Context

The existing voice-toggle decision established `--voice/--no-voice` as a required
capability, but runtime defaults still started with voice enabled in CLI flows.

A follow-up request required lightweight behavior by default so voice generation
becomes an explicit opt-in decision rather than an implicit startup cost.

## Content

### Options Considered

- Option 1: Keep voice enabled by default and rely on `--no-voice` for reduction.
  - Pros: Preserves earlier default behavior.
  - Cons: Adds avoidable resource cost and dependency surface to default runs.
- Option 2: Make subtitle-only the default and require `--voice` to enable TTS
  (chosen).
  - Pros: Lightweight baseline, clearer intentionality for heavier mode.
  - Cons: Users who expect audio must opt in explicitly.
- Option 3: Auto-toggle voice based on detected hardware.
  - Pros: Potentially adaptive behavior.
  - Cons: Less predictable UX and harder reproducibility across environments.

### Decision

Option 2 is selected.

CLI default behavior now starts in subtitle-only mode (`tts.enabled: false`), and
voice playback is explicitly enabled with `--voice` or configuration override.
This was implemented in both the model default (`docugym/config.py`) and default
runtime configuration (`configs/default.yaml`) to avoid drift.

### Pre-Mortem

- Failure mode: users assume audio should be present by default.
  - Mitigation: README quickstart/run-mode sections now call out voice opt-in.
- Failure mode: environment-level config overrides hide the baseline default.
  - Mitigation: config reference documents source precedence and explicit fields.
- Failure mode: troubleshooting text retains old assumptions.
  - Mitigation: troubleshooting guidance now treats subtitle-only as baseline mode.

## Changelog

- 2026-05-08: Created to record the default-policy shift from voice-first to
  subtitle-first CLI behavior.
