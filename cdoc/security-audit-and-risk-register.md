---
type: reference
tags: [security, audit, risk, supply-chain]
created: 2026-04-20
updated: 2026-05-08
status: active
related: [networking-ports-and-services.md, devcontainer-security-settings-review.md, github-actions-immutable-pinning.md, hashed-requirements-export-from-uv-lock.md, github-actions-hardening-measures-review.md, betterleaks-secret-scanning-evaluation-and-tuning.md, audit-container-cli-hardening-evaluation.md, stage-5-local-tts-streaming-audio.md, 2026-05-07-application-security-audit.md, 2026-05-08-application-security-audit.md, ci-scheduled-pip-audit-job.md, sb3-untrusted-repo-cli-confirmation.md, readonly-compose-profile-for-runp.md, security-audit-remediation-hub.md]
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

### Delta review (since last audit update)

- Baseline used: the 2026-05-08 follow-up audit in
  [2026-05-08-application-security-audit.md](2026-05-08-application-security-audit.md).
- Scope reviewed: `docugym/config.py`, `docugym/env.py`, `docugym/runtime.py`,
  `docugym/tune.py`, `docugym/cli.py`, `configs/*.yaml`,
  `docker-compose.yaml`, `scripts/serve_vlm.sh`, `pyproject.toml`, `uv.lock`,
  `requirements.txt`, README/spec docs, and focused tests.
- Verification performed:
  - `uv run ruff check .` passed.
  - `uv run pytest -q` passed: 95 tests, 1 existing pygame/pkg_resources warning.
  - `uv export --format requirements.txt --all-extras --group dev --no-emit-project --locked --output-file requirements.txt` completed.
  - A fresh temp export matched `requirements.txt` except for uv's generated
    output-path header; dependency bodies were byte-for-byte identical.
  - `DOCUGYM_VLM_HOST=0.0.0.0 ./scripts/serve_vlm.sh` refused to start unless
    the explicit public-bind acknowledgment is present.
- Security-profile changes observed:
  - CLI now requires explicit `--allow-untrusted-repo` opt-in (plus
    confirmation or `--yes`) for warning-only SB3 deserialization paths, and
    blocks untrusted custom repos without revision pins.
  - New `runp-ro` compose service/profile provides a read-only source-mount
    runtime path for non-edit workflows.
  - New `.github/workflows/pip-audit.yml` adds dependency CVE scanning on
    dependency-file PR/push changes plus weekly schedule.
  - SB3 trusted-repo enforcement now fails closed by default.
  - Shipped SB3 presets now pin Hugging Face model downloads to commit SHAs.
  - SB3 policy download now uses `huggingface_hub.hf_hub_download` with an
    optional `revision`, and local cache keys include the revision.
  - Voice and VLM runtime dependencies are declared as optional extras and
    included in the lock-derived hash export via `--all-extras`.
  - `dev`/`runp` compose services now set `no-new-privileges:true` and
    `cap_drop: ALL`, while retaining the writable source bind mount.
  - `scripts/serve_vlm.sh` now requires `DOCUGYM_VLM_ALLOW_PUBLIC=1` for any
    non-loopback bind.

### Critical findings

- None currently identified.

### High-priority findings

- None currently identified.

### Medium-priority findings

- Writable source bind mount (`.:/app`) still allows repository modification from inside
  the container for editable services even after added privilege barriers.
  - Location: `docker-compose.yaml` (`dev` and `runp` services).
  - Why it matters: `no-new-privileges:true` and `cap_drop: ALL` reduce kernel
    privilege expansion, but malicious code that already runs in-container can
    still alter host-side repository files through writable bind mounts.
    The new `runp-ro` service bounds this residual for non-edit workflows.
  - Potential malware source: compromised dependency, malicious downloaded artifact,
    or unsafe developer command in container session.
  - Confidence: `confident`.

- Residual dependency supply-chain exposure remains from ad-hoc installs that bypass
  lock-derived artifacts and documented extras.
  - Location: developer workflows that install directly from unconstrained
    requirement specifiers instead of `uv.lock` / exported hashed requirements.
  - Why it matters: voice/VLM optional dependencies are now locked and hash
    exported, but bypassing those flows can reintroduce mutable dependency
    resolution at install time.
  - Potential malware source: Python package index or transitive dependency takeover.
  - Confidence: `likely`.

### Low-priority findings

- Residual SB3 deserialization risk remains only when trusted-repo enforcement
  is explicitly bypassed via CLI opt-in (`--allow-untrusted-repo`), including
  non-interactive `--yes` usage.
  - Location: `docugym/env.py`, `docugym/cli.py`, and config-controlled
    `agent.enforce_trusted_repo` / `agent.sb3_revision`.
  - Why it matters: defaults now fail closed, custom untrusted repos require
    revision pins, and CLI prompts force explicit acknowledgement, but operators
    can still deliberately opt into deserialization risk for advanced workflows.
  - Potential malware source: third-party or attacker-controlled model repository.
  - Confidence: `likely`.

- `uvx` bootstrap for `ty` in pre-commit executes an externally fetched tool.
  - Location: `.pre-commit-config.yaml` (`uvx ty==0.0.32 check`).
  - Why it matters: additional supply-chain execution path in local developer flows.
  - Potential malware source: compromised package release or mirror.
  - Confidence: `likely`.

- VLM sidecar exposure can still broaden if users explicitly override
  `DOCUGYM_VLM_HOST` away from localhost and acknowledge the public bind.
  - Location: `scripts/serve_vlm.sh` (env override path).
  - Why it matters: broader bind scope can expose local inference endpoints to
    external network access depending on host firewall posture; the script now
    requires `DOCUGYM_VLM_ALLOW_PUBLIC=1` so this is no longer a one-variable
    accident.
  - Potential malware source: opportunistic local-network access.
  - Confidence: `likely`.

### Positive controls already present

- No host ports are currently published in `docker-compose.yaml` for `dev`/`runp`.
- Default runtime uses non-root user (`devuser`) in container images.
- CI workflow actions in `.github/workflows/ci.yml` are pinned to full commit
  SHAs with same-line version comments.
- CI workflow uses explicit least-privilege token scope (`permissions:
  contents: read`) and disables checkout credential persistence
  (`persist-credentials: false`).
- Third-party pre-commit hooks in `.pre-commit-config.yaml` are pinned to full
  commit SHAs with same-line version comments.
- `actionlint` is integrated in pre-commit via `actionlint-docker`.
- `zizmor` is integrated as a pre-commit hook for local GitHub Actions security
  analysis.
- `betterleaks` is integrated as a pre-commit hook, with `.betterleaks.toml`
  using path-scoped and line-targeted `AND` allowlists to reduce deterministic
  hash-pinning false positives while retaining default detectors.
- Dedicated `.github/workflows/zizmor.yml` runs zizmor in CI for GitHub Actions
  security scanning with SARIF upload.
- Dedicated `.github/workflows/pip-audit.yml` runs dependency CVE scanning in
  CI on dependency-file PR/push changes and weekly schedule.
- Dependabot version update automation is configured with cooldown policy in
  `.github/dependabot.yml` for `github-actions` and `uv` ecosystems.
- `requirements.txt` is exported from `uv.lock` with pinned versions and
  SHA-256 hashes, and omits editable project emission to preserve Docker
  bootstrap behavior.
- `.github/workflows/ci.yml` now validates that `requirements.txt` remains
  synchronized with lock-derived export semantics.
- Optional voice/VLM dependencies are declared as extras and included in the
  lock-derived hash export with `--all-extras`, reducing ad-hoc install pressure
  for `kokoro`, `sounddevice`, `soundfile`, and `vllm`.
- Stage 4 adds `httpx` runtime usage, and the dependency chain (`httpx`,
  `httpcore`, `anyio`, `h11`) is captured in lock-derived, hash-pinned
  `requirements.txt`.
- SB3 policy loading now has fail-closed trusted-repo controls by default,
  explicit trust-risk warnings, shipped commit SHA revision pins, and
  revision-aware cache paths for downloaded policy artifacts.
- CLI now requires explicit untrusted-repo opt-in and confirmation for
  warning-only SB3 deserialization paths, and requires revision pins for
  custom non-allowlisted repos.
- `scripts/serve_vlm.sh` now binds to `127.0.0.1` by default, reducing
  accidental network exposure of the local VLM endpoint.
- `scripts/serve_vlm.sh` now refuses non-loopback binds unless
  `DOCUGYM_VLM_ALLOW_PUBLIC=1` is explicitly set.
- `dev` and `runp` compose services now drop Linux capabilities and set
  `no-new-privileges:true`; their writable source bind mount remains a tracked
  residual risk.
- `runp-ro` compose service/profile adds a read-only runtime path with
  read-only source mount and tmpfs-backed writable runtime directories.
- A dedicated `audit` service runs dependency vulnerability checks in a more
  restricted container context (`read_only`, `tmpfs`, `no-new-privileges`,
  `cap_drop: ALL`, and read-only source mount).
- `audit` now uses a dedicated Docker build target with digest-pinned
  Chainguard Python base
  (`cgr.dev/chainguard/python@sha256:18a4fbda8c280978b6aa5329f7acd4dbb106876e76fdc87913855ebf4876f2ff`,
  Python 3.14.4, verified 2026-04-24)
  and pinned audit tool version (`pip-audit==2.9.0`), removing runtime tool
  bootstrap.
- `audit` compose service now drops all Linux capabilities (`cap_drop: ALL`),
  closing the last privilege gap in the scanning container. The Chainguard
  minimal base already provides no shell or CLI utilities; `cap_drop: ALL`
  adds a kernel-level capability barrier on top. See
  [audit-container-cli-hardening-evaluation.md](audit-container-cli-hardening-evaluation.md).

## Changelog

- 2026-04-20: Created initial rolling audit with severity-ranked findings.
- 2026-04-20: Updated after hardening compose defaults (removed unconfined seccomp and host IPC).
- 2026-04-22: Updated after CI workflow action SHA pinning; narrowed remaining
  action/tooling pinning risk to local pre-commit hooks.
- 2026-04-22: Updated after moving `requirements.txt` to lock-derived, hashed
  export from `uv.lock`; narrowed dependency supply-chain risk to bypass flows.
- 2026-04-23: Updated after pre-commit hook SHA pinning and `zizmor` integration;
  replaced resolved local hook pinning finding with dependency cooldown policy gap.
- 2026-04-23: Updated after CI workflow least-privilege hardening surfaced by
  `zizmor` (`permissions` scope and checkout credential persistence).
- 2026-04-23: Updated after adding Dependabot cooldown policy, `actionlint`
  pre-commit integration, and dedicated zizmor CI workflow.
- 2026-04-23: Updated after Betterleaks integration and `.betterleaks.toml`
  tuning for strict, context-scoped false-positive suppression.
- 2026-04-24: Audited post-Stage 4 changes since commit `58978c9`; documented
  new `audit` service hardening controls, sidecar binding exposure, and runtime
- 2026-04-26: Added `cap_drop: ALL` to `audit` compose service; updated
  positive controls to reflect full capability-drop posture.
  `pip-audit` bootstrap supply-chain tradeoff.
- 2026-04-24: Updated after pinning `audit` to a dedicated build target with
  pinned base image tag and pinned `pip-audit` version; removed runtime
  `pip install` bootstrap from compose execution.
- 2026-04-24: Updated `audit` base to a digest-pinned Chainguard Python image
  to reduce known container vulnerabilities reported by image linting.
- 2026-04-24: Refreshed Chainguard Python digest from `sha256:2c0fbbac…` to
  `sha256:18a4fbda…` (Python 3.14.4) after linter flagged outdated digest;
  verified via `docker pull cgr.dev/chainguard/python:latest`.
- 2026-05-07: Updated after adding SB3 trusted-repo controls, localhost-default
  VLM sidecar binding, and CI lock-export drift guard for `requirements.txt`.
- 2026-05-08: Verified all 2026-05-07 remediations in place; recorded
  follow-up audit in [2026-05-08-application-security-audit.md](2026-05-08-application-security-audit.md);
  added Low finding for missing scheduled `pip-audit` CI job; linked three
  open_task cdocs ([ci-scheduled-pip-audit-job.md](ci-scheduled-pip-audit-job.md),
  [sb3-untrusted-repo-cli-confirmation.md](sb3-untrusted-repo-cli-confirmation.md),
  [readonly-compose-profile-for-runp.md](readonly-compose-profile-for-runp.md)).
- 2026-05-08: Updated after closing the three 2026-05-08 open security tasks:
  added CLI untrusted SB3 confirmation/revision gate, introduced `runp-ro`
  readonly compose profile, and enabled automated `pip-audit` workflow with
  dependency-change and weekly schedule triggers.
- 2026-05-08: Rebalanced severities after remediation closure; moved the
  explicit-operator SB3 opt-in path from Medium to Low while keeping writable
  bind-mount tampering risk as Medium for editable services.
- 2026-05-07: Updated after remediating the application security audit findings:
  fail-closed SB3 trust defaults, HF revision pins, optional extras in hashed
  export, dev/runp capability drops, and VLM public-bind acknowledgment gate.

## Tasks Derived From Findings

- [x] Add trust controls for SB3 model loading (allowlist trusted repos, fail
  closed by default, warn on explicit opt-out, and document deserialization risk
  explicitly in CLI help).
- [x] Pin shipped SB3 Hugging Face model downloads to commit revisions and keep
  revision-specific cache paths.
- [x] Harden compose defaults by removing `seccomp=unconfined` and `ipc: host`
  from default services.
- [ ] If needed later, add an explicit opt-in override profile for exceptional
  debug/perf workflows requiring weaker isolation.
- [x] Strengthen optional runtime dependency controls by declaring voice/VLM
  extras and including them in the lock-derived hash export.
- [x] Add automated `pip-audit` or equivalent in CI if dependency vulnerability
  scanning should move from the dedicated compose audit path into GitHub Actions.
- [x] Constrain VLM sidecar bind interface by default (for example,
  `--host 127.0.0.1`) and require explicit opt-in for broader exposure.
- [x] Replace runtime `pip install --user pip-audit` in `audit` with a pinned
  and reproducible audit tool path (for example, baked image or pinned artifact).
- [x] Pin GitHub Actions in `.github/workflows/ci.yml` to immutable commit SHAs
  with same-line version comments.
- [x] Export `requirements.txt` from `uv.lock` with pinned versions and
  `--hash=sha256` entries (`uv export ... --no-emit-project`).
- [x] Pin pre-commit third-party hooks to immutable commit SHAs, with scheduled
  update process.
- [ ] Enable repository or organization policy requiring full-length SHA pinning
  for GitHub Actions.
- [x] Add a CI check that fails if `requirements.txt` drifts from
  `uv export --format requirements.txt --all-extras --group dev --no-emit-project --locked`.
- [x] Add dependency update automation with cooldown policy (Dependabot or
  Renovate) for at least `github-actions` and `uv`/`pip` ecosystems.
- [x] Evaluate and integrate `actionlint` (preferably with `shellcheck`) as a
  complementary workflow linter.
- [x] Add dedicated zizmor CI workflow for ongoing GitHub Actions security
  scanning and SARIF upload.
- [x] Evaluate and integrate Betterleaks as a pre-commit secret scanner with
  scoped tuning for deterministic hash-pinning patterns.
