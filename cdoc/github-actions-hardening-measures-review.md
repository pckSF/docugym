---
type: decision
tags: [security, ci, github-actions, supply-chain, pre-commit]
created: 2026-04-23
updated: 2026-04-23
status: active
related: [github-actions-immutable-pinning.md, security-audit-and-risk-register.md]
---

# GitHub Actions Hardening Measures Review

## Context

A hardening review was requested for several sources focused on GitHub Actions
security and supply-chain risk reduction, with a required minimum action to add
`zizmor` to local pre-commit hooks.

This review must align with existing cdoc decisions, especially:

- `github-actions-immutable-pinning.md`: CI workflows already use full commit-SHA
  pinning with same-line version comments.
- `security-audit-and-risk-register.md`: local pre-commit third-party hook pinning
  was previously tracked as an unresolved risk.

## Triage and Decomposition

- Operation type: `substantive write`.
- Decomposition:
  - Subtask 1: Research external recommendations and current repository state.
  - Subtask 2: Apply immediate hardening changes with low operational friction.
  - Subtask 3: Record accepted/deferred measures and track follow-up work.
- Dependency order: Subtask 1 -> Subtask 2 -> Subtask 3.

## Research

### Repository findings

- `.github/workflows/ci.yml` already pins all external actions to full commit SHAs
  with same-line version comments.
- `.pre-commit-config.yaml` used tag/version refs for third-party hooks and did
  not include `zizmor`.
- No dependency automation configuration was present (`.github/dependabot.yml`
  absent; no Renovate config file).

### External findings distilled

- `zizmor` should run both locally and in CI to prevent regressions in workflow
  security posture.
- `zizmor` has first-party pre-commit integration (`zizmorcore/zizmor-pre-commit`),
  and can also be integrated via `zizmorcore/zizmor-action` or manual SARIF upload.
- `actionlint` is complementary to `zizmor`, especially for workflow correctness
  and shell-related checks.
- Dependency cooldowns are a practical mitigation for opportunistic supply-chain
  attacks and are supported by both Dependabot (`cooldown`) and Renovate
  (`minimumReleaseAge`).
- Dependabot cooldown does not apply to security updates and has ecosystem support
  limits (e.g., semver-specific cooldown knobs are not available for all managers,
  including `github-actions`).
- Renovate `minimumReleaseAge` is useful but has caveats around transitive
  dependency updates and release timestamp availability.

### Prior cdoc constraints and conflicts

- Existing immutable pinning decision for workflows is already implemented, so
  recommendations about action SHA pinning are largely satisfied for CI workflows.
- Existing risk-register finding on local pre-commit hook pinning directly
  conflicts with leaving pre-commit hooks tag-pinned.

### Assumptions

- `confident`: Adding `zizmor` as a pre-commit hook is useful immediately for this
  repository, since workflows exist and are actively used.
- `confident`: Converting third-party pre-commit hook `rev` values to immutable
  SHAs reduces supply-chain risk in local hook execution.
- `likely`: Introducing cooldown automation would reduce exposure to short-lived
  malicious dependency releases.
- `uncertain`: Team preference between Dependabot and Renovate is not yet defined,
  so cooldown automation selection should remain a follow-up decision.

## Options Considered

#### Option 1: Minimal change (add `zizmor` only)
- **Description:** Add `zizmor` pre-commit hook and leave existing third-party
  hook refs unchanged.
- **Pros:** Meets the explicit minimum request with minimal edit surface.
- **Cons:** Leaves previously identified pre-commit hook pinning risk unresolved.

#### Option 2: Full immediate rollout (zizmor + actionlint + cooldown automation)
- **Description:** Add `zizmor`, add `actionlint`, and add full dependency update
  automation with cooldown in the same change.
- **Pros:** Maximizes immediate hardening coverage.
- **Cons:** Higher blast radius, introduces policy/process choices (Dependabot vs
  Renovate) without explicit repo owner preference, and increases review burden.

#### Option 3: Phased hardening
- **Description:** Implement immediate low-risk controls now (`zizmor` plus
  immutable pre-commit hook pinning), and track cooldown/actionlint automation as
  explicit follow-up tasks.
- **Pros:** Resolves current known local hook pinning risk while honoring the
  minimum user request and preserving manageable scope.
- **Cons:** Cooldown and actionlint protections are deferred, not immediate.

## Decision

Option 3 is chosen.

It satisfies the required minimum (`zizmor` integration) while also resolving an
already-documented medium-priority finding (local hook tag pinning). Compared
with Option 1, it avoids carrying a known unresolved risk. Compared with Option
2, it avoids bundling strategy-heavy automation choices before maintainership
preferences are explicitly set.

Implemented in this change:

- Add `zizmor` pre-commit hook using immutable commit SHA pinning.
- Convert existing third-party pre-commit hook `rev` values to immutable commit
  SHAs with same-line version comments.
- Apply low-risk workflow hardening surfaced by `zizmor` in CI:
  - explicit `permissions: contents: read`
  - `actions/checkout` configured with `persist-credentials: false`

Deferred as tracked follow-up tasks:

- Add dependency update automation with cooldown policy (Dependabot or Renovate).
- Evaluate `actionlint` integration (preferably with `shellcheck`).

### Follow-up Completion (2026-04-23)

The deferred follow-up tasks were completed in a subsequent hardening pass:

- Added `.github/dependabot.yml` with cooldown policy for
  `github-actions` and `uv` ecosystems.
- Added `actionlint` integration via pre-commit (`actionlint-docker`) with
  immutable SHA pinning.
- Added dedicated `.github/workflows/zizmor.yml` workflow using
  `zizmorcore/zizmor-action` for CI-based security scanning and SARIF upload.

## Pre-Mortem

- The pinned SHAs could become stale and miss upstream fixes.
  - Mitigation: keep scheduled dependency/tooling review tasks in the risk register.
- `zizmor` findings could become noisy and be ignored.
  - Mitigation: keep hook scope practical and incrementally address findings.
- Cooldown automation could be postponed indefinitely.
  - Mitigation: keep explicit open tasks in the risk register and enforce periodic
    security review checkpoints.

## Changelog

- 2026-04-23: Created decision note and implemented phased hardening step 1
  (`zizmor` pre-commit + immutable SHA pinning for third-party pre-commit hooks).
- 2026-04-23: Completed follow-up implementation for dependency cooldown
  automation, `actionlint` integration, and dedicated zizmor CI workflow.
