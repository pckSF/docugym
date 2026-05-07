---
type: decision
tags: [tooling, pyproject, ruff, pre-commit, ci]
created: 2026-05-07
updated: 2026-05-07
status: active
related: [stage-1-scaffolding-and-config-loader.md]
---
# Python Tooling Config Consolidation

## Context

The project accumulated configuration for Black, Ruff, isort, codespell, and
mypy, but the active automation no longer used all of those tools. The current
pre-commit workflow runs Ruff check, Ruff format, isort, actionlint, zizmor,
betterleaks, ty, and pytest. CI installs the dev group, verifies the generated
requirements export, runs Ruff check, and runs pytest.

## Research

- `.pre-commit-config.yaml` uses `ruff-check` with `--fix` and `ruff-format`;
  it does not run Black.
- `.github/workflows/ci.yml` runs `uv run ruff check .` and pytest; it does not
  run Black, mypy, or codespell.
- `pyproject.toml` still declared Black in the dev group and had a `[tool.black]`
  block, but Ruff is the formatter in the active hook set.
- `pyproject.toml` had dormant `[tool.codespell]` and `[tool.mypy]` blocks even
  though neither tool is installed in the dev group or invoked by hooks/CI.
- Ruff `0.15.11` reports only seven currently ignored rule families with active
  findings: `B008`, `B009`, `B010`, `PLR0912`, `PLR0913`, `PLR0915`, and
  `PLR2004`.
- Some old Ruff comments were stale or misleading: `B009`/`B010` descriptions
  were swapped, and comments such as "controversial" or "not yet implemented"
  did not record a project-specific reason.
- The project supports Python `>=3.11,<3.13`, so Ruff's target version should be
  the supported floor rather than the CI interpreter.

### Assumptions

- `confident`: Ruff format is the intended formatter because it is wired in
  pre-commit and Black is not.
- `confident`: Dormant tool configuration should be removed unless the tool is
  intentionally installed and run.
- `likely`: Keeping isort is still useful because pre-commit invokes it and Ruff
  does not currently select import-sort rules.

## Options Considered

### Option 1: Keep all historical tool configuration
- **Description:** Leave Black, codespell, mypy, broad Ruff ignores, and existing
  comments in place.
- **Pros:** Lowest immediate edit size.
- **Cons:** Leaves redundant dependencies, stale comments, and dormant settings
  that imply checks are happening when they are not.

### Option 2: Wire every configured tool into automation
- **Description:** Add Black, mypy, and codespell hooks or CI steps so every
  pyproject block is active.
- **Pros:** Makes the existing config meaningful and may improve coverage.
- **Cons:** Duplicates Ruff formatting with Black, adds new gates outside the
  user's requested cleanup, and creates broader remediation work for mypy or
  codespell findings.

### Option 3: Consolidate around the active toolchain
- **Description:** Remove Black, dormant mypy/codespell config, and inactive Ruff
  ignores; keep Ruff check/format, keep isort with pyproject as the source of
  import-sort style, and clarify the remaining suppressions.
- **Pros:** Matches current automation, reduces dependency surface, preserves the
  checks that already run, and makes ignore comments explain actual tradeoffs.
- **Cons:** Future mypy or codespell adoption will need fresh, explicit config
  instead of reusing dormant settings.

## Decision

Option 3 is chosen.

The active workflow already uses Ruff as both linter and formatter, so Black was
removed from the dev group and from `pyproject.toml`. The Ruff target version now
matches the supported Python floor, Ruff fix mode is left to the pre-commit hook
rather than the project-wide config, and the ignore list is limited to rules that
currently mask deliberate project tradeoffs. Dormant mypy and codespell config was
removed rather than left as implied-but-unused coverage.

## Pre-Mortem

- A future contributor may expect Black because the original stage specification
  mentioned it.
  - Mitigation: update the specification wording to Ruff check + Ruff format and
    keep this decision linked from the Stage 1 tooling note.
- Removing dormant mypy/codespell config may make later adoption less convenient.
  - Mitigation: treat reintroduction as a deliberate new tooling decision with
    fresh baselines and CI/pre-commit wiring.
- Trimming inactive Ruff ignores may surface new findings after future edits or
  Ruff upgrades.
  - Mitigation: keep comments specific and require new suppressions to record a
    project-specific reason.

## Changelog

- 2026-05-07: Created after consolidating Python tooling config around Ruff,
  isort, ty, pytest, and the existing security pre-commit hooks.
