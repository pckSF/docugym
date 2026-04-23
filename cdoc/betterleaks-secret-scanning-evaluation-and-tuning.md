---
type: decision
tags: [security, pre-commit, secret-scanning, betterleaks, supply-chain]
created: 2026-04-23
updated: 2026-04-23
status: active
related: [github-actions-hardening-measures-review.md, security-audit-and-risk-register.md]
---

# Betterleaks Secret Scanning Evaluation and Tuning

## Context

Secret scanning coverage was evaluated as an additional local hardening layer.
The required constraints were to keep immutable version pinning, avoid adding a
new CI gate for this tool, and reduce deterministic false positives without
broad allowlisting.

## Content

### Repository findings

- `.pre-commit-config.yaml` includes `betterleaks` pinned to an immutable commit
  SHA.
- `.betterleaks.toml` extends default detector behavior and uses path-scoped,
  line-targeted allowlists with `condition = "AND"`.
- Local validation was completed with `uv run pre-commit run betterleaks
  --all-files`.

### Options Considered

#### Option 1: Do not add Betterleaks
- **Pros:** No additional local tooling overhead.
- **Cons:** Leaves a preventable blind spot for accidental secret introduction.

#### Option 2: Add Betterleaks in both pre-commit and CI
- **Pros:** Stronger enforcement and central visibility.
- **Cons:** Adds CI complexity and duplicates a local-first prevention workflow.

#### Option 3: Add Betterleaks as pinned pre-commit hook with narrow tuning
- **Pros:** Catches leaks before commit while keeping immutable pinning and low
  operational friction.
- **Cons:** Depends on local hook adoption and disciplined allowlist scope.

### Decision

Option 3 is chosen.

Implemented in this change set:

- Added `betterleaks` to pre-commit with immutable SHA pinning.
- Added `.betterleaks.toml` with strict allowlists for deterministic hash-pinned
  lines that otherwise resemble secrets:
  - `requirements.txt` `--hash=sha256:<64-hex>` lines.
  - GitHub workflow `uses:` lines pinned to full 40-character SHAs (including
    optional action subpaths).
  - `.pre-commit-config.yaml` `rev:` lines pinned to full 40-character SHAs.
- Tightened regex anchoring for requirements hash lines and workflow `uses:`
  patterns after article-driven review.

### Pre-Mortem

- Over-broad allowlists could suppress real secret findings.
  - Mitigation: keep allowlists path-scoped, line-scoped, and `AND`-gated.
- Pin updates could drift and break or weaken scanner coverage.
  - Mitigation: update hooks through scheduled dependency maintenance.
- Local-only scanning may be bypassed in edge workflows.
  - Mitigation: re-evaluate CI enforcement if team process changes.

## Changelog

- 2026-04-23: Created decision note for Betterleaks adoption and local-only
  integration strategy.
- 2026-04-23: Recorded `.betterleaks.toml` tuning and regex hardening updates
  based on article-guided allowlist best practices.
