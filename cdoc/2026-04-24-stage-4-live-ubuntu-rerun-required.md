---
type: decision
tags: [stage-4, testing, ubuntu, validation, wsl, container]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-4-vlm-narration-sync.md, 2026-04-24-stage-3-real-ubuntu-display-results.md, 2026-04-24-stage-3-display-follow-up-validation-and-text-bands.md]
---

# 2026-04-24 Stage 4 Live Ubuntu Rerun Required

## Context

The current Stage 4 implementation has been developed and tested primarily from
within the dev container in a WSL-backed workflow. The next checkpoint needs a
real host-level validation pass on native Ubuntu again, similar to Stage 3
validation practice, before treating the stage as fully accepted.

## Research

- Prior project evidence already distinguishes between automated checks and
  host-observed behavior:
  - `2026-04-24-stage-3-real-ubuntu-display-results.md` records native Ubuntu
    execution as a separate validation event.
  - `2026-04-24-stage-3-display-follow-up-validation-and-text-bands.md` captures
    follow-up human-observed checks that cannot be proven by container logs alone.
- Stage 4 adds behavior that is specifically sensitive to host/runtime context:
  - local display timing and interaction,
  - local audio stack integration trajectory for Stage 5,
  - sidecar/network/process startup behavior on the host.
- Current dev container limitations relevant to acceptance confidence:
  - this environment cannot validate host Docker/Compose runtime (`docker`
    command unavailable in the active shell),
  - WSL/containerized runs are useful for fast iteration but are not equivalent
    to native Ubuntu user-facing behavior.

### Assumptions

- `confident`: Native Ubuntu rerun is required to confirm user-visible Stage 4
  behavior beyond unit/CLI checks.
- `likely`: WSL container runs remain useful for developer iteration and
  deterministic test execution.
- `likely`: A short, explicit rerun checklist reduces ambiguity at stage signoff.
- `uncertain`: Exact latency values observed in WSL container runs will match
  native Ubuntu host runs.

## Options Considered

#### Option 1: Accept Stage 4 based only on container + automated tests
- **Description:** Treat current test pass and container smoke checks as final
  acceptance evidence.
- **Pros:** Fastest path to close the stage.
- **Cons:** Risks missing host-specific display/runtime regressions and diverges
  from established Stage 3 validation discipline.
- **Why ruled out:** Rejected due lower confidence for user-facing runtime
  behavior.

#### Option 2: Require native Ubuntu rerun before final Stage 4 signoff (chosen)
- **Description:** Keep current implementation, but require a dedicated rerun on
  live Ubuntu outside WSL container context and record results in cdoc.
- **Pros:** Aligns with prior validation approach, increases confidence in real
  execution characteristics, and preserves traceable evidence.
- **Cons:** Requires additional manual test time and host availability.

#### Option 3: Split acceptance into provisional/final states
- **Description:** Mark the stage provisionally accepted in container, then
  upgrade to final after native rerun.
- **Pros:** Communicates progress while preserving quality gates.
- **Cons:** Adds state-management complexity without reducing actual validation
  work.
- **Why ruled out:** Rejected as unnecessary process overhead for this stage size.

## Decision

Option 2 is selected.

Stage 4 should be rerun and observed on native Ubuntu again (outside the WSL
container path) before final acceptance is treated as complete. Container and
CI checks remain required but not sufficient on their own for this user-facing
runtime milestone.

## Pre-Mortem

- Native rerun is skipped due schedule pressure, and host-specific regressions
  are discovered later.
  - Mitigation in note: explicit requirement and dedicated cdoc record.
- Rerun happens but without consistent command set, reducing comparability.
  - Mitigation in note: include command checklist in follow-up log entry.
- Team assumes rerun implies all future stages are host-validated automatically.
  - Mitigation in note: scope this requirement explicitly to Stage 4 signoff.
- Results are observed but not documented, losing organizational memory.
  - Mitigation in note: require cdoc follow-up entry for rerun outcomes.

## Changelog

- 2026-04-24: Created decision note requiring native Ubuntu rerun for Stage 4
  signoff instead of relying solely on WSL/container execution evidence.
