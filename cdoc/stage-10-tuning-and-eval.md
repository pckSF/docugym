---
type: decision
tags: [stage-10, tuning, evaluation, prompt, cli, readme]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-8-packaging-cli-and-readme.md, stage-9-mp4-recording.md, stage-6-async-orchestration-and-keyframe-selection.md]
---

# Stage 10 Tuning and Eval

## Context

Stage 10 in specification.md requires a tuning workflow that can run multiple
narrations over varied frames (`docugym tune prompt --env ... --samples 20`) and
a short README guide covering voice swaps, narration cadence tuning, and VLM
model-size changes.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: audit existing CLI/runtime for prompt-eval entry points.
- Subtask 2: choose Stage 10 command UX and implementation boundary.
- Subtask 3: implement command + tuning module + tests.
- Subtask 4: update README with a practical Stage 10 tuning guide.
- Subtask 5: validate with pre-commit and commit in logical blocks.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3 -> subtask 4 -> subtask 5.

## Research

### Existing codebase state before Stage 10 edits

- `docugym/cli.py` already had Stage 8/9 commands (`list-voices`, `list-envs`,
  `run`) but no Stage 10 tuning entry point.
- `docugym/narrator.py` already exposed `VLMNarrator.narrate_frame_sync(...)`
  and `NarrationContext`, which are sufficient for one-off frame narration in a
  non-async tuning command.
- `docugym/env.py` already had environment creation, random/scripted/SB3 agent
  paths, and trusted-repo handling for SB3 policy loading.
- Existing CLI tests in `tests/test_cli.py` used `CliRunner` + monkeypatch,
  which is the established pattern for command wiring validation.

### Prior cdoc decisions constraining Stage 10

- `stage-6-async-orchestration-and-keyframe-selection.md` requires stale-work
  dropping for live runtime smoothness; Stage 10 tooling should stay separate
  from that runtime pipeline to avoid introducing coupling.
- `stage-8-packaging-cli-and-readme.md` established Typer command ergonomics and
  README-first onboarding expectations.
- `stage-9-mp4-recording.md` reinforced optional feature wiring through CLI
  overrides layered on config defaults.

### External references consulted

- Typer subcommand docs (`tutorial/subcommands` and `add-typer`) confirm command
  groups are implemented with `app.add_typer(sub_app, name=...)`, supporting
  `docugym tune prompt` without overloading top-level command space.

### Implemented outcome summary

- Added a Stage 10 command group: `docugym tune prompt`.
- Added `docugym/tune.py` with `run_prompt_tuning(...)` that:
  - steps env frames with configurable stride for sample diversity,
  - supports random/scripted/SB3 agent paths,
  - calls sync narration per sample,
  - records per-sample narration latency.
- Added CLI/test coverage for command wiring and output.
- Added README Stage 10 guide with concrete examples for voice changes,
  narration interval tuning, and VLM model swaps.

### Assumptions

- confident: a dedicated `tune` subcommand group is the cleanest UX for Stage 10
  while preserving Stage 8 command discoverability.
- confident: stepping several env frames between sampled narrations (`step_stride`)
  improves frame diversity enough for prompt A/B iteration.
- likely: reusing config defaults plus optional CLI overrides is consistent with
  existing user expectations from `run` and Stage 9 recording controls.
- uncertain: ideal default stride for all envs may vary; further manual tuning
  might still be needed for specific games.

## Options Considered

#### Option 1: Add a top-level `tune-prompt` command only
- **Description:** Implement Stage 10 as one new top-level command.
- **Pros:** Minimal CLI structure changes.
- **Cons:** Scales poorly if Stage 10 grows additional tuning commands.
- **Why ruled out:** Rejected because command grouping is clearer and already
  supported by Typer with low additional complexity.

#### Option 2: Add a `tune` command group with `prompt` subcommand (chosen)
- **Description:** Introduce `docugym tune prompt` and keep tuning logic in a
  separate module used by CLI.
- **Pros:** Clear UX namespace, reusable logic, testable boundaries.
- **Cons:** Adds one new module and command group.

#### Option 3: Reuse `smoketest` to dump frames and narrate offline
- **Description:** Extend Stage 2 smoketest output and post-process frame files
  for narration comparisons.
- **Pros:** Reuses existing frame capture path.
- **Cons:** More disk I/O, slower feedback loop, and weaker continuity context.
- **Why ruled out:** Rejected because Stage 10 requires rapid iteration, and
  direct in-memory frame narration is simpler and faster.

## Decision

Option 2 is selected.

It keeps the CLI surface organized (`tune` namespace), reuses proven Stage 4/6
components (`make_env`, `VLMNarrator`, SB3 trust controls), and supports quick
prompt A/B loops without introducing file-based intermediate workflows from
Option 3. Compared with Option 1, it leaves room for future tuning subcommands
without flattening top-level command discoverability.

## Pre-Mortem

- Failure mode: sampled frames are too similar for useful prompt comparison.
  - Mitigation in note: expose `--step-stride` and document it as a diversity
    control in README.
- Failure mode: VLM endpoint is not ready and users misinterpret errors.
  - Mitigation in note: support `--wait-for-vlm` parity in Stage 10 command.
- Failure mode: SB3 tuning path loads untrusted model artifacts.
  - Mitigation in note: reuse existing trusted-prefix enforcement controls from
    Stage 2/6 env policy loading.
- Failure mode: README tuning guidance drifts from actual CLI behavior.
  - Mitigation in note: add command wiring tests and keep README examples aligned
    with real flags.

## Changelog

- 2026-05-07: Created Stage 10 decision note documenting tuning command design,
  implementation strategy, and evaluation guidance tradeoffs.
