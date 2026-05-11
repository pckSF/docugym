---
type: decision
tags: [code-review, remediation, performance, runtime, display, narrator, cli]
created: 2026-05-11
updated: 2026-05-11
status: active
related: [2026-05-07-code-review-idiomatic-and-performance-issues.md, 2026-05-07-code-review-remediation-scope.md, stage-6-async-orchestration-and-keyframe-selection.md, wrapper-mode-gym-api-integration.md]
---
# Source Bloat Remediation Pass

## Context

The attached source report identified duplicated wiring, avoidable hot-path work,
and some overgrown abstractions across `docugym/`. The request was to fix the
raised issues unless there was a good reason to defer them.

## Research

- `cdoc/_index.md`, `2026-05-07-code-review-remediation-scope.md`,
  `2026-05-07-code-review-idiomatic-and-performance-issues.md`,
  `stage-6-async-orchestration-and-keyframe-selection.md`, and
  `wrapper-mode-gym-api-integration.md` were re-read before implementation.
- The earlier 2026-05-07 remediation pass had already closed several findings
  that still appeared in the new report, including ffmpeg stderr draining,
  narrator async-client reuse, voice subtitle ownership, SB3 device/algorithm
  passthrough, clip filename counters, and wrapper queue/callback fixes.
- Current source inspection confirmed remaining local issues in env reset
  ownership, narrator payload duplication, trust helper duplication, PNG saver
  duplication, runtime protocol dispatch, sync loop-detection helpers, display
  surface allocation/wrapping, prompt global state, CLI dependency caching, and
  `list-envs` dead-branch handling.
- Current tests rely on the `docuwrapper` package-root export and CLI module
  globals as monkeypatch hooks, so removing the wrapper alias or the CLI hook
  surface would be a public/test-contract migration rather than a local cleanup.
- The keyframe sampled-copy behavior was retained because it protects wrapper
  mode from env-buffer aliasing; removing that copy would save work but would
  conflict with the previous remediation note's immutable-frame safety goal.

### Assumptions

- confident: `make_env` should seed action spaces only and let callers own the
  first reset because all call sites already reset when they need observations.
- confident: shared helpers are appropriate for PNG saving and sync-loop checks
  because the behavior is identical across callers.
- confident: display frame surfaces and scaled surfaces can be cached by size
  without changing visible layout behavior.
- likely: `hasattr`/bound-method dispatch is clearer and cheaper than
  `runtime_checkable` protocol `isinstance` checks for narrator/speaker calls.
- likely: large CLI option-resolution consolidation should be its own follow-up
  because it touches command UX and many monkeypatched tests.
- uncertain: deeper exception narrowing should be paired with an explicit runtime
  error model so intentionally non-fatal recording/narration degradation remains
  visible without breaking long runs unexpectedly.

## Options Considered

#### Option 1: Fix every report item in one pass
- **Description:** Apply local cleanups, CLI option-resolution refactors,
  runtime/wrapper orchestration changes, public API removals, and exception-policy
  changes together.
- **Pros:** Maximizes immediate checklist closure.
- **Cons:** Mixes low-risk duplication removal with API migration and
  architecture work; raises regression risk in the canonical async runtime and
  wrapper mode.
- **Why ruled out:** Rejected because prior cdoc decisions keep wrapper mode and
  canonical runtime behavior stable, and several report items require wider UX or
  architecture planning.

#### Option 2: Implement high-confidence local remediations and record deferrals
- **Description:** Fix issues with clear local boundaries and existing test
  coverage, then document larger or conflicting findings as intentional follow-up
  work.
- **Pros:** Removes real duplication and hot-path waste while preserving public
  behavior; keeps validation focused and reviewable.
- **Cons:** Leaves some legitimate refactors open, especially CLI option merging
  and shared orchestration.

#### Option 3: Documentation-only triage
- **Description:** Do not edit source; only convert the report into cdoc tasks.
- **Pros:** Lowest regression risk.
- **Cons:** Leaves easy, verified fixes undone despite the request to remediate.
- **Why ruled out:** Rejected because several findings had obvious local fixes
  and full test coverage could validate them immediately.

## Decision

Option 2 is selected.

This pass fixes the report items that are local, behavior-preserving, and covered
by tests. It avoids the broader command-resolution, public API, exception-policy,
and orchestration changes because those need a dedicated design note or migration
plan.

## Implemented Outcome

- Removed the redundant `env.reset(seed=seed)` from `make_env`; runtime,
  smoketest, display smoketest, tuning, and wrapper call sites continue to reset
  once when they need observations.
- Added shared `image_io.save_frame_png` and reused it from `env.py` and
  `clips.py`.
- Reused env trust helpers from `cli.py` and stopped `_load_cli_dependency` from
  mutating `globals()` while preserving monkeypatch hookability.
- Added shared `async_utils.run_async_from_sync` and reused it from runtime,
  narrator, and TTS sync wrappers.
- Extracted narrator payload construction into one helper and made sync narration
  encode directly instead of offloading image encoding from an already-sync call.
- Replaced runtime narrator/speaker `runtime_checkable` protocol dispatch with
  direct method lookup and switched runtime task supervision to `asyncio.TaskGroup`.
- Cached display source/scaled frame surfaces by size, stopped global
  `pygame.quit()` on display close, and made subtitle wrapping cached and
  incremental instead of measuring whole candidate lines per word.
- Replaced the one-element prompt-state list with an explicit module global.
- Removed the dead `list-envs` `found` branch and widened TTS abbreviation masking
  for common short forms.
- Updated tests for the new `make_env` reset contract.

## Deferred Findings

- CLI option-resolution consolidation remains open because it touches `run`,
  `smoketest`, and `tune prompt` UX plus many test monkeypatch seams.
- Removing `docuwrapper` is deferred because it is an exported public convenience
  API covered by package-root tests and wrapper docs.
- Full runtime/wrapper orchestration consolidation remains deferred under the
  existing wrapper-mode decision because it changes ownership boundaries rather
  than only removing duplication.
- Broad exception narrowing remains deferred until the runtime has an explicit
  error-reporting contract for non-fatal narration, recording, policy, and audio
  degradation paths.
- Keyframe sampled copies remain because they prevent aliasing against mutable env
  render buffers in wrapper mode.
- Dynamic generation of `__all__` remains deferred because the active Ruff rules
  require literal exports to keep `TYPE_CHECKING` imports lint-clean.

## Validation

- `.venv/bin/python -m ruff check docugym tests` passed.
- `.venv/bin/python -m ruff format --check docugym tests` passed.
- `.venv/bin/python -m pytest` passed: 95 tests, 1 upstream pygame/pkg_resources
  deprecation warning.

## Pre-Mortem

- Failure mode: removing the factory reset changes callers that implicitly relied
  on `make_env` to reset. Mitigation: all in-tree call sites reset explicitly and
  `tests/test_env.py` now locks the factory contract.
- Failure mode: display surface caching mishandles frame-size changes. Mitigation:
  cached surfaces are keyed by raw and scaled sizes and recreated when dimensions
  change.
- Failure mode: method-lookup dispatch accepts a callable with the wrong
  signature. Mitigation: this is equivalent to the previous runtime Protocol
  checks in practice, which only checked member presence; failures still surface
  at the call site with normal tracebacks.
- Failure mode: deferred items are mistaken for forgotten work. Mitigation: the
  deferred list names each item and why it was kept out of this pass.

## Changelog

- 2026-05-11: Created after implementing and validating the local source-bloat
  remediation pass.
