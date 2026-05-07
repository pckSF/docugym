---
type: decision
tags: [stage-5, tts, audio, kokoro, subtitles, security]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-4-vlm-narration-sync.md, 2026-04-27-voice-toggle-subtitle-only-mode.md, stage-6-async-orchestration-and-keyframe-selection.md, security-audit-and-risk-register.md]
---

# Stage 5 Local TTS and Voice Toggle

## Context

A pass was requested to reconcile implementation status against
specification.md and cdoc decisions, close open security tasks that are
actionable in-repo, and then implement the next stage in sequence.

## Triage and Decomposition

- Operation type: substantive write.
- Subtask 1: determine implementation status against stage plan.
- Subtask 2: close actionable security follow-ups from the rolling audit.
- Subtask 3: implement Stage 5 TTS/audio and voice-toggle behavior.
- Dependency order: subtask 1 -> subtask 2 -> subtask 3.

## Research

### Stage-state audit

- Stage 1 to Stage 4 code paths are present in the current repo.
- Stage 4 remains marked with a native Ubuntu rerun requirement in
  2026-04-24-stage-4-live-ubuntu-rerun-required.md.
- The codebase still used a Stage 4 synchronous runtime loop as the active
  orchestration model, which is expected until Stage 6.
- Stage 5-specific modules (local TTS engine, sounddevice callback pipeline,
  runtime voice toggle wiring) were not implemented before this pass.

### Open security tasks before this pass

From security-audit-and-risk-register.md, the actionable open tasks in current
repository scope were:

- Add trust controls for SB3 policy loading.
- Constrain VLM sidecar bind interface to localhost by default.
- Add a CI check that fails when requirements.txt drifts from lock export.

Tasks requiring org-level policy control or additional governance remain out of
single-repo code-edit scope.

### Implementation findings

- SB3 policy loading now supports trusted repo prefix allowlists, logs warnings
  for untrusted repo ids, and supports strict enforcement mode.
- CLI help now explicitly documents SB3 deserialization trust risk.
- VLM sidecar startup defaults to host binding on 127.0.0.1, with explicit env
  var override for broader exposure.
- CI now verifies lock-derived requirements export consistency.
- Stage 5 adds:
  - docugym/tts.py with a Kokoro-backed sentence synthesizer using
    asyncio.to_thread.
  - docugym/audio.py with queue-fed sounddevice callback playback.
  - runtime wiring for voiced narration and subtitle-only mode.
  - config toggle tts.enabled and CLI --voice/--no-voice support.

### Assumptions

- confident: Stage 5 can ship on top of the Stage 4 synchronous loop, with
  full async orchestration deferred to Stage 6 by design.
- confident: warning-plus-enforcement trust controls materially reduce SB3
  deserialization risk compared to unrestricted loading.
- likely: localhost-by-default sidecar binding is the safest default while
  preserving explicit override flexibility.
- uncertain: real-world audio smoothness and startup latency still require
  native host validation under live GPU/audio stacks.

## Options Considered

#### Option 1: Stage 5 only, defer security tasks
- Description: implement TTS/audio and voice toggle now, leave open security
  tasks unchanged.
- Pros: narrows implementation scope.
- Cons: leaves known, actionable security findings unresolved.
- Why ruled out: rejected because the request explicitly included tying up open
  security tasks first.

#### Option 2: Security-only hardening, defer Stage 5
- Description: close security tasks and postpone TTS/audio stage work.
- Pros: lowest runtime regression risk.
- Cons: does not advance the staged implementation plan.
- Why ruled out: rejected because the request asked to implement the next stage
  after security closure.

#### Option 3: Targeted security closure plus Stage 5 on synchronous runtime (chosen)
- Description: close actionable security follow-ups, then implement Stage 5
  components without pre-emptively jumping to Stage 6 async redesign.
- Pros: satisfies both security and stage-progression goals while containing
  architecture churn.
- Cons: narration loop remains synchronous; heavy narration+TTS can still stall
  frame stepping until Stage 6 queue orchestration lands.

## Decision

Option 3 is selected.

It closes in-repo, high-value security gaps while moving the product forward to
Stage 5. Compared with Option 1, it does not leave known security tasks open.
Compared with Option 2, it keeps momentum on the staged roadmap without forcing
an early Stage 6 rewrite.

## Pre-Mortem

- Failure mode: voiced mode fails on hosts missing runtime audio/TTS deps.
  - Mitigation: runtime falls back to subtitle-only mode with warning logs.
- Failure mode: SB3 strict trust enforcement blocks legitimate private repos.
  - Mitigation: trust prefixes are configurable and enforcement is opt-in.
- Failure mode: CI drift check becomes noisy if command semantics change.
  - Mitigation: check uses lock export command + git diff on requirements.txt,
    matching repository workflow exactly.
- Failure mode: Stage 5 appears complete but host UX regressions remain.
  - Mitigation: keep Stage 4/5 host rerun and manual acceptance notes as
    explicit follow-up validation gates.

## Changelog

- 2026-05-07: Created decision note covering stage-state audit, security task
  closure strategy, and Stage 5 implementation approach.
- 2026-05-07: Linked Stage 6 decision note for async orchestration and
  keyframe-based narration backpressure handling.
