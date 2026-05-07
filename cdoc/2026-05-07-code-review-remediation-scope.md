---
type: decision
tags: [code-review, remediation, performance, runtime, recording, narrator, wrapper]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [2026-05-07-code-review-idiomatic-and-performance-issues.md, 2026-05-07-docstring-standardization-pass.md]
---
# Code Review Remediation Scope

## Context

The 2026-05-07 static review identified 63 idiomatic, correctness, and
performance findings across the active DocuGym codebase. This pass triages the
report into a first implementation batch that can be fixed, tested, and committed
without destabilizing the canonical async runtime or wrapper API.

## Research

### Codebase findings

- `runtime.py` is the canonical async path and already owns bounded queues,
  display action handling, TTS, audio, and recording hooks.
- `wrapper.py` remains a synchronous Gym wrapper with a background narration
  worker; several helper modules have already been extracted to reduce drift, but
  a shared orchestration core does not exist yet.
- `recording.py` streams raw frames through ffmpeg and currently keeps stderr as
  a pipe until close, which is the highest correctness-risk finding.
- `narrator.py` already exposes async and sync methods, making async-client reuse
  and off-thread image encoding feasible without changing public constructor
  semantics.
- Display frame-surface reuse, display-thread extraction, pydantic settings-source
  restructuring, and audio ring-buffer work require either benchmarking, external
  API reshaping, or a wider architecture pass.

### Prior cdoc constraints

- `stage-6-async-orchestration-and-keyframe-selection.md` makes the async runtime
  the preferred production pipeline and requires bounded backpressure.
- `stage-9-mp4-recording.md` requires recording failures to keep gameplay and
  narration running, making recorder hardening preferable to recording-driven
  control-flow changes.
- `wrapper-mode-gym-api-integration.md` acknowledges partial orchestration
  duplication and frames shared-core extraction as follow-on work rather than a
  prerequisite for wrapper usability.

### Assumptions

- confident: the ffmpeg stderr pipe finding should be fixed immediately because
  it is a concrete deadlock risk with a small, testable implementation.
- confident: runtime subtitle ownership, bounded latency samples, callback
  isolation, and recorder cleanup timing are local fixes that do not change user
  workflow.
- likely: VLM async-client reuse and off-thread JPEG encoding improve hot-path
  latency while preserving the direct `httpx` client boundary chosen for Stage 4.
- likely: downsampled keyframe deltas retain enough signal for the existing
  heuristic while reducing full-frame allocation pressure.
- uncertain: display surface caching and non-blocking display pacing should be
  benchmarked under real SDL/GPU stacks before replacing the current pygame
  path.

## Options Considered

#### Option 1: Fix all 63 findings in one commit
- **Description:** Treat every audit item as mandatory for this pass, including
  shared orchestration extraction, display-threading, pydantic source redesign,
  and audio ring-buffer work.
- **Pros:** Maximizes checklist closure and removes more known issues at once.
- **Cons:** Very large blast radius, mixes correctness fixes with speculative
  performance rewrites, and risks invalidating the tested runtime/wrapper
  behavior established by prior decisions.
- **Why ruled out:** Rejected because several findings need design or benchmark
  evidence before implementation and would make the commit too broad to review
  safely.

#### Option 2: Target high-confidence local fixes and document deferrals (chosen)
- **Description:** Implement the correctness and low-risk performance fixes that
  have clear local boundaries, add targeted tests, and explicitly leave larger
  architectural findings documented for follow-up.
- **Pros:** Addresses concrete risk quickly, preserves existing public behavior,
  keeps test coverage focused, and gives future work a clean backlog.
- **Cons:** Leaves some audit items open, including the shared-orchestrator and
  display-pacing findings.

#### Option 3: Documentation-only triage
- **Description:** Do not edit code; only classify findings into future work.
- **Pros:** Lowest regression risk and fastest cdoc cleanup.
- **Cons:** Leaves known local correctness and performance issues unresolved.
- **Why ruled out:** Rejected because the request explicitly asks to fix raised
  issues unless there is a reason to deviate.

## Decision

Option 2 is selected.

This pass will fix the audit findings that are local, well-understood, and
testable in the current repository: ffmpeg stderr draining and write allocation,
runtime subtitle race and metric cleanup, narrator client/encoding hot paths,
keyframe delta sampling, wrapper queue/callback consistency, audio queue helper
reuse, small CLI/TTS/clip/tune polish, and SB3 device/algorithm extensibility.

The pass will defer shared orchestration extraction, display-thread or full
surface-cache rewrites, pydantic settings-source redesign, audio ring-buffer
replacement, and large runtime signature grouping. Those are valid follow-ups,
but they need either a dedicated design note, benchmark evidence, or a public API
migration plan.

## Implemented Outcome

This pass implemented the following audit remediations:

- Runtime: replaced the paused env polling loop with an event, removed queue
  polling timeouts, bounded latency samples, sorted percentiles once, removed
  unused semaphores, made render frames contiguous/read-only at the fan-out
  boundary, let TTS own voiced subtitles, moved `on_narration` callbacks off the
  event loop, added non-fatal callback handling, split drop/failure metrics, added
  richer exception logging, and captured recorder end time before audio shutdown.
- Recording: drained ffmpeg stderr on a background thread, wrote video frames via
  memoryview, and reused a module-level silence block for padding.
- Narrator: reused a persistent `httpx.AsyncClient` for async narration calls,
  encoded images off the event loop, switched low-detail image payloads to JPEG,
  validated the base URL, separated readiness request timeout, narrowed readiness
  exception handling, and normalized the system prompt indentation.
- Wrapper: reduced subtitle queue depth to one, ran narration through one
  long-lived worker event loop when an async narrator is available, closed async
  narrators on wrapper shutdown, avoided fragile callback closures, and updated
  narration/subtitle state atomically.
- Shared and polish fixes: reused the queue helper in audio output, downsampled
  keyframe delta checks while storing sampled copies to avoid aliasing, added SB3
  device and explicit algorithm plumbing, avoided splitting common titles in TTS,
  added clip filename counters, reused `humanize_env_id` in tuning, and guarded
  empty prompt-tuning latency output.

Targeted tests were added or updated for narrator client reuse/JPEG payloads,
recording stderr draining, voiced subtitle ownership, callback failure isolation,
SB3 device/algorithm passthrough, TTS title splitting, and the new type surface.

## Deferred Findings

The following audit items remain intentionally open:

- Shared orchestration extraction (`runtime.py` and `wrapper.py`) is deferred as
  a dedicated architecture task because it changes ownership boundaries and public
  behavior more than this remediation commit should.
- Display non-blocking pacing, persistent surface reuse, and text-render caching
  are deferred pending SDL/pygame benchmarks on real display hardware.
- Wrapper lazy frame-copy changes are deferred because the current eager copy is
  conservative for correctness; removing it should be paired with a shared frame
  immutability contract across wrapper and runtime.
- Runtime dataclass config grouping and typed `run_session_sync` kwargs are
  deferred as an API migration rather than a bug fix.
- Audio ring-buffer replacement, pydantic settings-source redesign, root-relative
  default paths, common Typer option extraction, SB3 filename manifest lookup, and
  sample-accurate recorder audio offsets remain valid follow-ups outside this
  local fix batch.

## Pre-Mortem

- Failure mode: local fixes subtly change runtime timing or subtitle behavior.
  - Mitigation in note: add focused regression tests around voiced subtitles,
    callback isolation, and recording lifecycle rather than relying only on the
    broad smoke suite.
- Failure mode: VLM client reuse leaks clients when sync wrappers are used.
  - Mitigation in note: expose an explicit async close path and keep sync calls
    isolated from persistent async clients unless a stable worker loop owns them.
- Failure mode: downsampled keyframe deltas miss meaningful visual changes.
  - Mitigation in note: keep thresholds configurable and leave benchmark/manual
    tuning as follow-up if trigger quality regresses.
- Failure mode: deferred items are mistaken for forgotten work.
  - Mitigation in note: record each deferral reason here and keep the source
    audit linked from the index.

## Changelog

- 2026-05-07: Created remediation-scope decision after reading the audit,
  related cdoc decisions, implementation modules, and targeted tests.
- 2026-05-07: Updated with implemented remediation outcomes, added tests, and
  explicit deferrals after pre-commit validation passed.
- 2026-05-07: Linked the docstring-standardization log note for documentation
  quality follow-up traceability.
