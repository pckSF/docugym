---
type: open_task
tags: [security, docker, compose, hardening, runtime]
created: 2026-05-08
updated: 2026-05-08
status: archived
related: [2026-05-08-application-security-audit.md, devcontainer-security-settings-review.md, audit-container-cli-hardening-evaluation.md, security-audit-and-risk-register.md, security-audit-remediation-hub.md]
---
# Read-Only Compose Profile for Non-Edit Run Workflows

## Context

The 2026-05-07 audit added `security_opt: [no-new-privileges:true]` and
`cap_drop: [ALL]` to the `dev` and `runp` services, retaining the writable
`.:/app` bind mount as a deliberate residual. The 2026-05-08 follow-up
audit re-confirmed the writable mount as a Medium finding: in-container
code can still tamper with host-visible repository files (e.g.
`.git/hooks/post-commit`, `docugym/__init__.py`, `pyproject.toml`),
neutralizing the non-root-user mitigation.

## Content

### Options considered

#### Option 1: Keep only writable `runp` and `dev` (rejected)
- **Description:** Retain current behavior and accept writable-bind risk.
- **Pros:** Zero compose complexity increase.
- **Cons:** Non-edit runtime sessions keep unnecessary host-write exposure.
- **Why ruled out:** Leaves the documented Medium finding unbounded for default
  runtime container usage.

#### Option 2: Make `runp` read-only by default (rejected)
- **Description:** Convert existing `runp` directly to read-only posture.
- **Pros:** Strong default hardening.
- **Cons:** Breaks existing workflows that intentionally write repository-side
  outputs during rapid iteration.
- **Why ruled out:** Introduces avoidable workflow churn for active development.

#### Option 3: Add dedicated `runp-ro` profile/service (chosen)
- **Description:** Keep current writable services and add a hardened non-edit
  path with read-only mount and tmpfs-backed writable runtime locations.
- **Pros:** Reduces attack surface for non-edit runs without disrupting
  established editing workflows.
- **Cons:** Adds one more service/profile to document and maintain.

### Decision

Chose **Option 3** to bound writable-bind risk to explicit editing/iteration
services while preserving backward-compatible container workflows.

### Pre-Mortem

- **Failure mode:** Users keep using writable `runp` out of habit.
  **Mitigation in this note:** README now documents `runp-ro` as the hardened
  non-edit path and keeps role separation explicit.
- **Failure mode:** Read-only rootfs breaks runtime due missing writable paths.
  **Mitigation in this note:** `runp-ro` includes tmpfs for `/tmp`,
  `/home/devuser/.cache`, and `/app/out`.
- **Failure mode:** Security drift between `runp` and `runp-ro`.
  **Mitigation in this note:** `runp-ro` mirrors `runp` GPU reservation plus
  `no-new-privileges` and `cap_drop: ALL` controls.

### Outcome

Implemented in `docker-compose.yaml` and `README.md` with a new `runp-ro`
service under profile `readonly`, read-only source bind mount, read-only
filesystem posture, and tmpfs-backed writable runtime paths.

## Changelog

- 2026-05-08: Created.
- 2026-05-08: Archived as completed after adding `runp-ro` and documenting
  profile selection guidance.
