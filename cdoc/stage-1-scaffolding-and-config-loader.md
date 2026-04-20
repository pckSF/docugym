---
type: decision
tags: [scaffolding, config, ci, stage-1]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [stage-2-gym-env-wrapper-and-smoketest.md]
---

# Stage 1 Scaffolding and Config Loader

## Context

The repository started as a minimal skeleton with no Python package, no CLI entrypoint,
no GitHub Actions workflow, and a placeholder requirements list. Stage 1 in
specification.md requires a runnable CLI (`docugym --help`), a YAML-backed config
loader with environment variable overrides, and baseline lint/test automation.

## Research

- The repository currently has only top-level infra files and no application module.
- Existing lint tooling is partially configured: Ruff is present in `.pre-commit-config.yaml`
  and the TOML lints are detailed, but Black is not explicitly wired as requested by
  Stage 1.
- `pydantic-settings` is available and supports `YamlConfigSettingsSource` with explicit
  source ordering via `settings_customise_sources`, which allows environment variables
  to override YAML values.
- The current Docker/devcontainer workflow installs from `requirements.txt`, so keeping
  that file aligned with Stage 1 dependencies is necessary for reproducible onboarding.

### Assumptions

- `likely`: Stage 1 should create the `docugym/` package and keep naming consistent
  with the existing project identifier.
- `confident`: A fixed default YAML path (`configs/default.yaml`) plus optional CLI
  override is sufficient for Stage 1.
- `likely`: A minimal CI workflow that runs Ruff and pytest without GPU dependencies is
  the correct scope for this stage.
- `uncertain`: Future stages may require revisiting package metadata once heavy ML
  dependencies are introduced.

## Options Considered

### Option 1: Keep current project name and add only minimal CLI/config stubs
- **Description:** Preserve `docugym` metadata and add a small script-level implementation.
- **Pros:** Lowest immediate churn.
- **Cons:** Misaligned with the Stage 1 package-first architecture and harder to scale.

### Option 2: Create `docugym` package with typed config models and Typer CLI
- **Description:** Introduce a proper package, strongly typed settings, and script entrypoint
  now, while keeping runtime behavior lightweight.
- **Pros:** Matches specification naming, provides stable extension points for later stages,
  cleanly supports YAML + env override behavior.
- **Cons:** More initial file creation and metadata updates.

### Option 3: Use plain dataclasses + manual YAML parsing + `argparse`
- **Description:** Avoid pydantic-settings and keep dependencies smaller.
- **Pros:** Lower abstraction, less dependency lock-in.
- **Cons:** Reimplements validation/override behavior already solved by pydantic-settings;
  diverges from spec recommendations.

## Decision

Option 2 is chosen. It aligns naming and structure with Stage 1 goals while keeping the
implementation maintainable for subsequent stages. Compared with Option 1, it avoids
future migration churn. Compared with Option 3, it preserves robust, typed configuration
handling with less custom parsing code.

## Pre-Mortem

- Config precedence confusion may cause env vars to lose to YAML defaults.
  Mitigation: Explicit source ordering and a test that verifies override behavior.
- Dependency drift between `pyproject.toml` and `requirements.txt` may break devcontainer
  setup.
  Mitigation: Update both files in the same change and run installs from the active venv.
- CI may fail due to missing test bootstrap.
  Mitigation: Add a lightweight config-focused pytest that does not require external
  services or GPUs.

## Changelog

- 2026-04-20: Created.
- 2026-04-20: Updated project naming references to docugym.
- 2026-04-20: Linked follow-on Stage 2 decision note.
