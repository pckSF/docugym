---
type: open_task
tags: [security, ci, supply-chain, dependencies, pip-audit]
created: 2026-05-08
updated: 2026-05-08
status: archived
related: [2026-05-08-application-security-audit.md, security-audit-and-risk-register.md, hashed-requirements-export-from-uv-lock.md, github-actions-immutable-pinning.md, security-audit-remediation-hub.md]
---
# Add Scheduled `pip-audit` CI Job for Hash-Pinned Requirements

## Context

The 2026-05-08 audit ([2026-05-08-application-security-audit.md](2026-05-08-application-security-audit.md)) recorded
this as the single most important Low finding: CI today runs only `ruff
check` and `pytest`. `pip-audit` exists only as an opt-in `audit` Compose
service that an operator must invoke locally. Combined with the strict
`--require-hashes` posture in `requirements.txt`, a known-CVE version of a
transitive dependency can stay pinned indefinitely until a manual run or
unrelated Dependabot bump.

## Content

### Options considered

#### Option 1: Audit only when dependency files change (rejected)
- **Description:** Trigger scan solely on PR/push changes to dependency
  manifests.
- **Pros:** Minimal CI runtime overhead.
- **Cons:** Misses newly disclosed CVEs for already-pinned versions.
- **Why ruled out:** Does not address disclosure-lag risk identified by the
  audit.

#### Option 2: Run `pip-audit` on every PR/push only (rejected)
- **Description:** Scan every code change but without any schedule.
- **Pros:** High visibility for in-flight code changes.
- **Cons:** Still misses CVEs disclosed after merge when no further PRs land.
- **Why ruled out:** Leaves a monitoring gap during low-change periods.

#### Option 3: Hybrid trigger model (chosen)
- **Description:** Run scan on dependency-change PR/push events and on a weekly
  schedule.
- **Pros:** Catches newly disclosed CVEs while containing unnecessary CI load.
- **Cons:** Does not scan every non-dependency PR.

### Decision

Chose **Option 3** because the weekly schedule is required to detect
post-disclosure CVEs independent of file churn, while path-filtered PR/push
triggers provide fast feedback for dependency updates without adding noise to
every unrelated PR.

### Pre-Mortem

- **Failure mode:** Weekly cadence delays awareness of a fresh high-impact CVE.
  **Mitigation in this note:** Dependency-change PR/push events still run
  immediately; local `docker compose run --rm audit` remains available for ad-hoc
  checks.
- **Failure mode:** Workflow breaks due tool/action drift.
  **Mitigation in this note:** Actions are pinned to full SHAs and tool version
  is pinned to `pip-audit==2.9.0`.
- **Failure mode:** Teams assume Dependabot fully replaces vulnerability scans.
  **Mitigation in this note:** This note explicitly keeps CVE scanning and
  version-update automation as separate controls.

### Outcome

Implemented `.github/workflows/pip-audit.yml` with:

- Path-filtered `pull_request` and `push` (`main`) triggers for dependency files.
- Weekly scheduled run.
- Least-privilege `permissions: contents: read`.
- Full-SHA action pinning and `uv tool run --from pip-audit==2.9.0 ...`.
- Failure-on-advisory behavior via default `pip-audit` exit semantics.

## Changelog

- 2026-05-08: Created.
- 2026-05-08: Archived as completed after adding hybrid-trigger pip-audit
  workflow in GitHub Actions.
