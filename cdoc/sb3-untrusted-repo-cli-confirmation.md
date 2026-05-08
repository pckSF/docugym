---
type: open_task
tags: [security, cli, sb3, deserialization, ux]
created: 2026-05-08
updated: 2026-05-08
status: archived
related: [2026-05-08-application-security-audit.md, 2026-05-07-application-security-audit.md, security-audit-and-risk-register.md, security-audit-remediation-hub.md]
---
# CLI Confirmation Gate for Untrusted SB3 Repos and Unpinned Revisions

## Context

The 2026-05-07 remediation flipped `agent.enforce_trusted_repo` to `True`
by default and added optional `revision` pinning, closing the high-severity
default-config path. The 2026-05-08 follow-up audit confirmed those
defaults but recorded a Medium residual: a single YAML edit
(`enforce_trusted_repo: false`) downgrades the loader to a logger warning
before deserializing the artifact, and custom repo ids without a `revision`
pin still resolve to mutable `HEAD`.

## Content

### Options considered

#### Option 1: Keep config-only trust controls (rejected)
- **Description:** Keep relying on `agent.enforce_trusted_repo` and warning logs
  without CLI boundary checks.
- **Pros:** No CLI surface changes; no new UX prompts.
- **Cons:** A single YAML edit silently re-enables warning-only
  deserialization; mutable custom repos remain easy to misconfigure.
- **Why ruled out:** This leaves the core residual noted by the 2026-05-08
  audit unchanged.

#### Option 2: Remove all untrusted-repo loading support (rejected)
- **Description:** Force hard-fail behavior for every untrusted repo with no
  opt-out path.
- **Pros:** Strongest baseline safety.
- **Cons:** Blocks legitimate local workflows with private or personal SB3
  checkpoints.
- **Why ruled out:** Over-constrains intended advanced usage and conflicts with
  the repository's explicit local experimentation scope.

#### Option 3: CLI-scoped explicit opt-in + revision pin checks (chosen)
- **Description:** Require `--allow-untrusted-repo`, interactive confirmation
  (or `--yes`), and revision pins for custom repos.
- **Pros:** Preserves advanced workflows while preventing silent re-entry into
  warning-only deserialization paths.
- **Cons:** Adds CLI complexity and an additional confirmation branch.

### Decision

Chose **Option 3** because it retains legitimate custom-repo usage while
forcing explicit acknowledgment for deserialization risk and preventing mutable
HEAD downloads for non-allowlisted repositories.

### Pre-Mortem

- **Failure mode:** Operators bypass confirmation with `--yes` in copied scripts.
  **Mitigation in this note:** The gate still requires the separate explicit
  `--allow-untrusted-repo` flag, preserving two independent opt-in signals.
- **Failure mode:** Future CLI command paths forget to apply the gate.
  **Mitigation in this note:** Logic is centralized in one helper and exercised
  by dedicated CLI tests.
- **Failure mode:** Revision requirement blocks legitimate trusted defaults.
  **Mitigation in this note:** Revision pin requirement applies only to repos
  outside trusted prefixes.

### Outcome

Implemented in `docugym/cli.py` with:

- New `--allow-untrusted-repo` and `--yes` options for `smoketest`, `run`, and
  `tune prompt`.
- CLI-side custom-repo revision requirement (`--revision` or
  `agent.sb3_revision`).
- Centralized trust-resolution helper that requires explicit opt-in before any
  warning-only deserialization path is used.
- Regression coverage in `tests/test_cli.py` and docs updates in `README.md`
  and `docs/config_reference.md`.

## Changelog

- 2026-05-08: Created.
- 2026-05-08: Archived as completed after implementing explicit CLI opt-in,
  revision-pin checks for custom repos, and regression tests.
