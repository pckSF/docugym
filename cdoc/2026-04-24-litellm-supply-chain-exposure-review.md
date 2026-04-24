---
type: decision
tags: [security, supply-chain, dependencies, litellm, stage-4]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [security-audit-and-risk-register.md, hashed-requirements-export-from-uv-lock.md, stage-4-vlm-narration-sync.md]
---

# 2026-04-24 LiteLLM Supply-Chain Exposure Review

## Context

A March 2026 supply-chain incident affected LiteLLM package releases
(`1.82.7` and `1.82.8`) with credential-stealing payloads. Stage 4 introduces
new inference-related code paths and dependency changes, so dependency exposure
was reviewed before and after implementation.

## Research

- External incident source reviewed:
  - Heise report: compromised LiteLLM package versions `1.82.7` and `1.82.8`,
    published temporarily on PyPI, with recommendations for credential rotation
    if those versions were installed.
- Repository dependency evidence:
  - No `litellm` dependency appears in `pyproject.toml`, `uv.lock`, or
    `requirements.txt`.
  - Stage 4 implementation uses direct `httpx` calls to a local OpenAI-compatible
    endpoint (`/v1/chat/completions`) and does not introduce LiteLLM.
- Supply-chain controls preserved:
  - `requirements.txt` remains lock-derived and SHA-hashed from `uv.lock`.
  - Added dependency (`httpx`) is pinned in lock/export output with transitive
    hash coverage.
- Validation status:
  - Full test suite passed after dependency update and lock/export refresh.

### Assumptions

- `confident`: This repository is not directly affected by the compromised
  LiteLLM releases because LiteLLM is not present in runtime dependencies.
- `likely`: Existing lock+hash controls reduce but do not eliminate all
  third-party supply-chain risk.
- `likely`: Direct `httpx` integration keeps operational surface smaller than
  introducing an additional inference proxy dependency.
- `uncertain`: Future transitive dependency advisories may emerge; periodic audit
  tooling should still be added in CI for earlier detection.

## Options Considered

#### Option 1: Introduce LiteLLM anyway for provider abstraction
- **Description:** Add LiteLLM to normalize model endpoint interactions.
- **Pros:** Unified provider interface if multiple providers are needed later.
- **Cons:** Unnecessary dependency for current local vLLM-only use case,
  increased supply-chain surface, and immediate sensitivity to LiteLLM release
  trust.
- **Why ruled out:** Rejected because current architecture only needs direct
  local endpoint access.

#### Option 2: Use direct `httpx` calls with lock-derived dependency pinning (chosen)
- **Description:** Keep Stage 4 endpoint integration in-project via `httpx` and
  maintain existing lock+hash workflow.
- **Pros:** Minimal dependency surface, clear trust boundary, deterministic
  dependency artifacts already aligned with existing security controls.
- **Cons:** Less abstraction for future multi-provider expansion.

#### Option 3: Freeze implementation until complete automated CVE tooling is added
- **Description:** Block Stage 4 delivery until an automated audit workflow is
  merged in CI.
- **Pros:** Stronger immediate assurance posture.
- **Cons:** Delays Stage 4 delivery despite no direct LiteLLM exposure and
  existing hash-pinned install controls.
- **Why ruled out:** Rejected as disproportionate for this stage; capture CI
  audit automation as follow-up security work.

## Decision

Option 2 is selected.

Stage 4 proceeds with direct `httpx` integration and no LiteLLM dependency.
Given the specific compromised LiteLLM versions and verified absence of LiteLLM
in this repository, there is currently no known direct exposure from this
incident in the project dependency set.

## Pre-Mortem

- Future contributor adds LiteLLM without incident-aware version policy.
  - Mitigation in note: explicitly document current non-use of LiteLLM and
    reason for avoiding it in Stage 4.
- Dependency artifacts drift from lock-derived exports.
  - Mitigation in note: keep lock + requirements export update in same change
    and preserve hashed export command.
- New vulnerabilities emerge in newly added dependencies (`httpx` stack).
  - Mitigation in note: track follow-up to add routine CI vulnerability checks.
- Security conclusion is over-generalized beyond the verified evidence.
  - Mitigation in note: scope statement to "currently no known direct exposure"
    and keep uncertainty explicit.

## Changelog

- 2026-04-24: Created incident response decision note; verified no LiteLLM
  dependency exposure and documented Stage 4 dependency posture.
