---
type: decision
tags: [security, supply-chain, dependencies, uv, docker]
created: 2026-04-22
updated: 2026-04-22
status: active
related: [security-audit-and-risk-register.md]
---

# Hashed Requirements Export From uv.lock

## Context

A follow-up supply-chain hardening review requested parity between the new
GitHub Actions SHA pinning controls and Python dependency installation.

This repository installs dependencies in Docker from `requirements.txt` via:
`uv pip install -r requirements.txt`.

A prior cdoc finding flagged dependency supply-chain exposure from version ranges
and non-hash installs in `requirements.txt`/`pyproject.toml` and Docker install
flows. Stage 1 decisions also require `requirements.txt` to remain aligned with
project dependencies for reproducible onboarding.

## Research

- Current install flows:
  - CI installs from `uv.lock` (`uv sync --group dev`).
  - Docker builds install from `requirements.txt` using `uv pip install -r`.
- `.dockerignore` allows only `requirements.txt` in build context, so Docker
  dependency bootstrap must work from that file alone.
- `uv export` supports `requirements.txt` output and includes hashes by default
  (omitted only with `--no-hashes`).
- `uv export` supports dependency-group controls and `--no-emit-project`.
- Default `uv export` output in this repository includes `-e .`; that would
  break the current Docker flow because the project source is not mounted during
  dependency bootstrap.
- `uv` docs note that keeping both `uv.lock` and `requirements.txt` is generally
  not preferred, but this repository currently needs a pip-compatible artifact
  for Docker build integration.

### Prior Decision Constraints

- `security-audit-and-risk-register.md` identified non-hash dependency installs
  as a medium-priority risk to reduce.
- `stage-1-scaffolding-and-config-loader.md` requires keeping
  `requirements.txt` aligned with project dependencies for reproducible setup.

### Assumptions

- `confident`: Hash-pinned requirements reduce tampering risk in pip-compatible
  install paths.
- `confident`: `--no-emit-project` is required to keep the existing Docker
  bootstrap path working.
- `likely`: Including `--group dev` preserves current behavior where dev tools
  are present in the dev container venv.
- `uncertain`: Without an automated check, developers may update `uv.lock`
  without re-exporting `requirements.txt`.

## Options Considered

#### Option 1: Keep manually maintained range-based requirements
- **Description:** Continue with `>=,<` specs and no hashes in
  `requirements.txt`.
- **Pros:** Small file, easy manual edits.
- **Cons:** Leaves the identified supply-chain gap open for Docker installs.

#### Option 2: Manually craft pinned+hashed requirements from lock metadata
- **Description:** Build and maintain hash lines by hand using `uv.lock` package
  entries.
- **Pros:** Full control over file contents.
- **Cons:** Error-prone, high maintenance burden, and likely to drift.

#### Option 3: Generate `requirements.txt` from `uv.lock` via `uv export`
- **Description:** Export pinned+hashed requirements with a fixed command that
  omits editable project emission.
- **Pros:** Reproducible generation, hash integrity, lower human error, aligns
  with existing Docker install interface.
- **Cons:** Larger generated file and requires a documented regeneration step.

## Decision

Option 3 is chosen.

`requirements.txt` is now generated from `uv.lock` using:

`uv export --format requirements.txt --group dev --no-emit-project --locked --output-file requirements.txt`

This approach closes the non-hash dependency-install gap in Docker while
preserving current build semantics and dev dependency availability.

## Pre-Mortem

- `uv.lock` changes but `requirements.txt` is not regenerated.
  - Mitigation: keep generation command in file header; add CI drift check in a
    follow-up task.
- Someone removes `--no-emit-project` and reintroduces `-e .`, breaking Docker.
  - Mitigation: document this caveat and verify absence of `-e .` during review.
- Large cross-platform hash sections increase PR noise.
  - Mitigation: accept generated-file churn as a security tradeoff and keep
    updates intentional.
- Dev-group expectations shift and export contents change unexpectedly.
  - Mitigation: keep explicit group flag in the generation command and monitor
    diffs.

## Changelog

- 2026-04-22: Created decision and moved `requirements.txt` to hash-pinned,
  lock-derived export with `--no-emit-project`.
