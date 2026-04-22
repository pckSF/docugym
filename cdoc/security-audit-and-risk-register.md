---
type: reference
tags: [security, audit, risk, supply-chain]
created: 2026-04-20
updated: 2026-04-22
status: active
related: [networking-ports-and-services.md, devcontainer-security-settings-review.md, github-actions-immutable-pinning.md, hashed-requirements-export-from-uv-lock.md]
---

# Security Audit and Risk Register

## Context

This file is a rolling security audit for the repository. Update it whenever
security-relevant code, dependencies, container settings, CI behavior, or
networking assumptions change.

## Content

### How to use this rolling audit

- Add or update findings after any meaningful infrastructure or dependency change.
- Keep findings grouped by severity, with each item carrying a confidence label.
- Move resolved findings to archived notes only when their risk is fully removed.
- Keep tasks at the end of this file synchronized with current findings.

### Critical findings

- None currently identified.

### High-priority findings

- Untrusted model/policy deserialization path in runtime policy loading.
  - Location: `docugym/env.py` (`load_sb3_policy` -> `stable_baselines3.*.load`).
  - Why it matters: model artifacts loaded by SB3 rely on Python deserialization
    mechanics; loading untrusted artifacts can result in arbitrary code execution.
  - Potential malware source: third-party or attacker-controlled model repository.
  - Confidence: `likely`.

### Medium-priority findings

- Writable source bind mount (`.:/app`) allows repository modification from inside
  the dev container.
  - Location: `docker-compose.yaml` (`dev` and `runp` services).
  - Why it matters: if malicious code executes in-container, it can alter
    host-side repository files through the bind mount.
  - Potential malware source: compromised dependency, malicious downloaded artifact,
    or unsafe developer command in container session.
  - Confidence: `confident`.

- Residual dependency supply-chain exposure from ad-hoc installs that bypass
  lock-derived artifacts.
  - Location: developer workflows that install directly from unconstrained
    requirement specifiers instead of `uv.lock` / exported hashed requirements.
  - Why it matters: bypassing locked and hashed artifacts can reintroduce
    mutable dependency resolution at install time.
  - Potential malware source: Python package index or transitive dependency takeover.
  - Confidence: `likely`.

- Local pre-commit third-party hooks are not commit-SHA pinned.
  - Location: `.pre-commit-config.yaml`.
  - Why it matters: tag drift or compromised upstream release can change code
    executed in local developer hook flows.
  - Potential malware source: third-party hook repository compromise.
  - Confidence: `likely`.

### Low-priority findings

- `uvx` bootstrap for `ty` in pre-commit executes an externally fetched tool.
  - Location: `.pre-commit-config.yaml` (`uvx ty==0.0.32 check`).
  - Why it matters: additional supply-chain execution path in local developer flows.
  - Potential malware source: compromised package release or mirror.
  - Confidence: `likely`.

### Positive controls already present

- No host ports are currently published in `docker-compose.yaml` for `dev`/`runp`.
- Default runtime uses non-root user (`devuser`) in container stages.
- CI workflow actions in `.github/workflows/ci.yml` are pinned to full commit
  SHAs with same-line version comments.
- `requirements.txt` is exported from `uv.lock` with pinned versions and
  SHA-256 hashes, and omits editable project emission to preserve Docker
  bootstrap behavior.

## Changelog

- 2026-04-20: Created initial rolling audit with severity-ranked findings.
- 2026-04-20: Updated after hardening compose defaults (removed unconfined seccomp and host IPC).
- 2026-04-22: Updated after CI workflow action SHA pinning; narrowed remaining
  action/tooling pinning risk to local pre-commit hooks.
- 2026-04-22: Updated after moving `requirements.txt` to lock-derived, hashed
  export from `uv.lock`; narrowed dependency supply-chain risk to bypass flows.

## Tasks Derived From Findings

- [ ] Add trust controls for SB3 model loading (allowlist trusted repos, warn on
  untrusted repo ids, and document deserialization risk explicitly in CLI help).
- [x] Harden compose defaults by removing `seccomp=unconfined` and `ipc: host`
  from default services.
- [ ] If needed later, add an explicit opt-in override profile for exceptional
  debug/perf workflows requiring weaker isolation.
- [ ] Strengthen supply-chain controls (prefer lock-driven installs and add
  automated `pip-audit` or equivalent in CI).
- [x] Pin GitHub Actions in `.github/workflows/ci.yml` to immutable commit SHAs
  with same-line version comments.
- [x] Export `requirements.txt` from `uv.lock` with pinned versions and
  `--hash=sha256` entries (`uv export ... --no-emit-project`).
- [ ] Pin pre-commit third-party hooks to immutable commit SHAs, with scheduled
  update process.
- [ ] Enable repository or organization policy requiring full-length SHA pinning
  for GitHub Actions.
- [ ] Add a CI check that fails if `requirements.txt` drifts from
  `uv export --format requirements.txt --group dev --no-emit-project --locked`.
