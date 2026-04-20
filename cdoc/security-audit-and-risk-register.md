---
type: reference
tags: [security, audit, risk, supply-chain]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [networking-ports-and-services.md]
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

- Development container weakens isolation with `seccomp=unconfined` and `ipc: host`.
  - Location: `docker-compose.yaml` (`dev` service).
  - Why it matters: increased blast radius if malicious code executes in container.
  - Potential malware source: compromised dependency, malicious downloaded artifact,
    or unsafe developer command in container session.
  - Confidence: `confident`.

- Dependency supply-chain exposure due to version ranges and non-hash installs.
  - Location: `requirements.txt`, `pyproject.toml`, and install flows in `Dockerfile`.
  - Why it matters: compromised upstream package versions could be pulled during
    rebuilds or dependency sync operations.
  - Potential malware source: Python package index or transitive dependency takeover.
  - Confidence: `confident`.

- CI and tool bootstrap actions are not commit-SHA pinned.
  - Location: `.github/workflows/ci.yml` and `.pre-commit-config.yaml`.
  - Why it matters: tag drift or compromised upstream release can change code
    executed in CI or local hooks.
  - Potential malware source: third-party GitHub Action or hook repository compromise.
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

## Changelog

- 2026-04-20: Created initial rolling audit with severity-ranked findings.

## Tasks Derived From Findings

- [ ] Add trust controls for SB3 model loading (allowlist trusted repos, warn on
  untrusted repo ids, and document deserialization risk explicitly in CLI help).
- [ ] Provide a hardened compose profile that avoids `seccomp=unconfined` and
  `ipc: host` by default, with opt-in overrides only when required.
- [ ] Strengthen supply-chain controls (prefer lock-driven installs and add
  automated `pip-audit` or equivalent in CI).
- [ ] Pin GitHub Actions and pre-commit third-party hooks to immutable commit SHAs,
  with scheduled update process.
