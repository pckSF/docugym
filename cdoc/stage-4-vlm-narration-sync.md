---
type: decision
tags: [stage-4, narration, vlm, vllm, httpx, sync]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-3-display-layer.md, networking-ports-and-services.md, 2026-04-24-litellm-supply-chain-exposure-review.md]
---

# Stage 4 VLM Narration (Synchronous First)

## Context

Stage 4 in `specification.md` requires introducing frame-to-text narration via a
single local VLM call while keeping the implementation intentionally synchronous
for first delivery. The required runtime behavior is:

- call a local OpenAI-compatible endpoint on a fixed cadence (`narrate_every`),
- update subtitles with generated narration,
- log latency so p50/p95 can be measured,
- keep current Stage 3 display architecture intact.

Stage 3 already established a dedicated display module and a thin CLI layer. The
next increment should preserve those boundaries and avoid introducing async
pipeline complexity reserved for Stage 6.

## Research

- Existing repo state before this change:
  - No narrator client module existed.
  - No `docugym run` command existed; only `smoketest` and `display-smoketest`.
  - Config already contained VLM/narration fields (`vlm.*`, `narration.*`), but
    there was no code consuming them.
- Stage constraints from prior notes:
  - `stage-3-display-layer.md` recommends keeping display concerns isolated from
    CLI parsing and minimizing coupling to future orchestration changes.
  - `networking-ports-and-services.md` already treats `http://localhost:8000/v1`
    as the local VLM endpoint and requires readiness checks before narration runs.
- Implementation research decisions validated in code:
  - Add `docugym/narrator.py` as an async HTTP client (`httpx`) with a sync
    wrapper for Stage 4 loop integration.
  - Encode frames as PNG base64 data URLs in OpenAI-compatible multimodal
    message format.
  - Keep a dedicated run loop in `docugym/runtime.py` that performs synchronous
    narration every N frames and reports p50/p95 latency.
  - Add `scripts/serve_vlm.sh` with the Stage 4 vLLM launch recipe.
- Verification performed:
  - Added tests for narrator payload construction/readiness polling.
  - Added tests for runtime narration cadence and CLI `run` wiring.
  - Full test suite passes after implementation (`26 passed`).

### Assumptions

- `confident`: A synchronous wrapper around an async narrator is the fastest path
  to Stage 4 DoD while preserving an upgrade path to Stage 6 async pipeline.
- `likely`: Fixed-cadence narration (`--narrate-every`) is sufficient for Stage 4;
  richer keyframe heuristics belong to Stage 6.
- `likely`: Logging narration latency in-process is adequate initial telemetry for
  p50/p95 checks before adding dedicated metrics exporters.
- `uncertain`: Some SB3 Atari checkpoints may not match raw env observations; a
  random-action fallback on policy inference failure is acceptable in Stage 4.

## Options Considered

#### Option 1: Add synchronous HTTP calls directly inside CLI command
- **Description:** Keep everything in `docugym/cli.py`, including frame encoding,
  HTTP requests, and run-loop logic.
- **Pros:** Lowest file count and quickest first implementation.
- **Cons:** Violates prior separation guidance from Stage 3, reduces testability,
  and makes Stage 6 async refactor harder.
- **Why ruled out:** Rejected to avoid coupling rendering/orchestration internals
  to CLI argument parsing.

#### Option 2: Add dedicated narrator module + runtime loop (chosen)
- **Description:** Implement `docugym/narrator.py` for multimodal calls and
  `docugym/runtime.py` for Stage 4 sync run-loop orchestration.
- **Pros:** Clear boundaries, easier tests, direct compatibility with current
  display module, and straightforward migration to Stage 6 queue tasks.
- **Cons:** Slightly larger code surface in this stage.

#### Option 3: Use LiteLLM SDK/proxy for provider abstraction
- **Description:** Route Stage 4 narration through LiteLLM instead of direct
  OpenAI-compatible HTTP calls.
- **Pros:** Potential multi-provider abstraction in one place.
- **Cons:** Adds an unnecessary dependency and extra operational layer for a
  single local endpoint; increases supply-chain surface.
- **Why ruled out:** Rejected because direct `httpx` calls are sufficient and
  lower-risk for local single-provider Stage 4.

## Decision

Option 2 is selected.

This approach preserves Stage 3 module boundaries while delivering Stage 4
requirements with minimal architectural debt. Compared with Option 1, it keeps
CLI thin and testable. Compared with Option 3, it avoids adding an unnecessary
dependency/proxy layer and keeps the trust boundary small.

## Pre-Mortem

- Local VLM endpoint is not ready when `run` starts, causing immediate failures.
  - Mitigation in note: add `--wait-for-vlm` and timeout polling against
    `/models` before entering gameplay loop.
- Narration latency spikes can visibly stall the synchronous loop.
  - Mitigation in note: explicitly accept Stage 4 stutter and record p50/p95;
    defer non-blocking queue design to Stage 6.
- SB3 policy mismatch with live env observation spaces causes inference errors.
  - Mitigation in note: fallback to random actions when SB3 inference fails,
    while logging warnings for diagnosis.
- Prompt/payload mismatch against OpenAI-compatible multimodal schema causes
  empty outputs.
  - Mitigation in note: test payload shape and normalize response content with a
    safe fallback subtitle sentence.

## Changelog

- 2026-04-24: Created Stage 4 decision with synchronous narrator/runtime design,
  sidecar script, CLI run command, latency telemetry, and test coverage.
