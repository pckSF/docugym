---
type: decision
tags: [runtime, cli, refactor, naming, final-setup]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-6-async-orchestration-and-keyframe-selection.md, stage-8-packaging-cli-and-readme.md, stage-10-tuning-and-eval.md, 2026-05-07-code-review-idiomatic-and-performance-issues.md]
---

# Final Setup Runtime and Naming Consolidation

## Context

The project implementation has moved beyond incremental stage delivery, but the
active code paths and user-facing docs still exposed stage-labeled APIs and
wording. This created two problems: confusion about which runtime is canonical,
and avoidable maintenance overhead from duplicate or legacy entry points.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: inventory all stage-labeled artifacts in runtime APIs, CLI wiring,
  tests, and active user docs.
- Subtask 2: remove legacy runtime flow and converge to one canonical runtime
  API surface.
- Subtask 3: propagate symbol changes across CLI/tests and remove stage wording
  from active user-facing documentation.
- Subtask 4: validate with pre-commit hooks and record outcome.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3 -> subtask 4.

## Research

### Codebase findings

- docugym/runtime.py contained two runtime tracks:
  - run_stage4_session: legacy synchronous narration loop.
  - run_stage6_session + run_stage6_session_sync: async bounded-queue pipeline.
- docugym/cli.py run command already called the async runtime path, but used a
  stage-labeled function name.
- tests/test_runtime.py still directly tested the removed legacy sync runtime.
- tests/test_cli.py monkeypatched stage-labeled runtime symbols.
- README.md still framed quickstart and tuning with stage-labeled sections,
  despite the implementation being functionally unified.

### Prior cdoc decisions constraining this change

- stage-6-async-orchestration-and-keyframe-selection.md establishes async queue
  orchestration and stale-candidate dropping as the preferred runtime behavior.
- stage-8-packaging-cli-and-readme.md establishes preset discovery commands and
  user-facing CLI ergonomics that should remain stable through refactor.
- stage-10-tuning-and-eval.md establishes tune prompt command behavior and
  should remain aligned with runtime naming updates.

### Assumptions

- confident: run_stage4_session is no longer required for the final product
  surface because the canonical run path already uses async orchestration.
- confident: renaming run_stage6_session_sync and Stage4RunResult to stage-neutral
  symbols improves coherence without changing runtime behavior.
- likely: historical stage notes should remain as archival decision records,
  while active code and README should present the final unified system.
- uncertain: external users may import legacy runtime symbol names directly; no
  compatibility shim was retained in this pass.

## Options considered

#### Option 1: Keep stage-named wrappers and only rewrite wording
- Description: Preserve all stage-prefixed symbols and remove stage language only
  from docs/help text.
- Pros: Lowest break risk for downstream imports.
- Cons: Leaves duplicate conceptual surfaces and keeps historical implementation
  boundaries in the active API.
- Why ruled out: Rejected because it does not satisfy the goal of one coherent
  final runtime surface.

#### Option 2: Consolidate on one runtime API and remove legacy stage path (chosen)
- Description: Delete the legacy synchronous runtime flow, rename the async path
  to canonical symbols, and update all active callers/tests/docs accordingly.
- Pros: Single clear runtime entrypoint, lower maintenance burden, clearer user
  mental model.
- Cons: Potential API break for direct imports of old stage-prefixed names.

#### Option 3: Purge stage terms from all historical notes/spec artifacts
- Description: Rewrite cdoc and specification history to remove stage language
  everywhere.
- Pros: Maximum naming consistency across the entire repository.
- Cons: Destroys historical traceability and muddles chronological decision
  context.
- Why ruled out: Rejected because stage language in historical records is part
  of the project timeline and remains useful as archive context.

## Decision

Option 2 is selected.

This approach removes ambiguity in the active implementation surface while
preserving the validated async runtime behavior from the prior decision set. It
avoids Option 1's dual-surface drift and avoids Option 3's historical data loss.

## Pre-mortem

- Failure mode: external scripts importing old symbols fail.
  - Mitigation in note: call out absence of compatibility aliases and keep this
    as a follow-up if downstream breakage appears.
- Failure mode: tests lose coverage that previously exercised sync narration.
  - Mitigation in note: preserve behavioral assertions around the canonical
    async runtime path (including reward triggers, backpressure, mute/save, and
    recording).
- Failure mode: docs and code diverge again with mixed terminology.
  - Mitigation in note: keep stage labels out of active code and README; retain
    historical stage language only in archival notes.

## Changelog

- 2026-05-07: Created decision note for final setup consolidation of runtime
  naming, CLI wiring, tests, and active user docs.
