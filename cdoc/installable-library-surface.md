---
type: decision
tags: [packaging, library-api, config, prompts, cli]
created: 2026-05-08
updated: 2026-05-08
status: active
related: [stage-8-packaging-cli-and-readme.md, wrapper-mode-gym-api-integration.md, final-setup-runtime-and-naming-consolidation.md, stage-10-tuning-and-eval.md]
---

# Installable Library Surface

## Context

DocuGym already has a proper package directory, project metadata, and console-script
entry point, but installed usage still behaves too much like a source checkout. The
default config path and preset discovery depend on `configs/` relative to the current
working directory, README install guidance focuses on development sync, and the package
root exposes only the wrapper API. Users should be able to clone the repository, run
`python3 -m pip install .` or `uv pip install .`, and then use DocuGym from the target
environment through normal imports and the `docugym` CLI.

## Content

### Implementation Phases

- Phase 0: create this decision note and keep it updated at each implementation phase.
- Phase 1: make wheel/sdist contents explicit and add PEP 561 typing metadata.
- Phase 2: add installed-safe config preset resolution using packaged resources.
- Phase 3: expose a broader, documented package-root API for library use.
- Phase 4: add a prompt customization API for global and per-instance narrator prompts.
- Phase 5: update README/API docs and tests, then run validation and install smoke checks.

### Options Considered

#### Option 1: Document `pip install .` only
- **Description:** Leave code unchanged and add install commands to README.
- **Pros:** Lowest implementation cost.
- **Cons:** Installed CLI still depends on caller CWD for config presets and does not
  expose the requested library surface.
- **Why ruled out:** Documentation alone would not satisfy installed usage from arbitrary
  working directories.

#### Option 2: Package presets and broaden library API in place (chosen)
- **Description:** Keep the flat package layout, bundle preset YAML files into the wheel,
  resolve defaults through `importlib.resources`, broaden root imports, and add prompt
  customization helpers.
- **Pros:** Preserves current source-tree workflows while making installed usage real.
- **Cons:** Adds API surface that must be documented and kept stable.

#### Option 3: Move configs under `docugym/` permanently
- **Description:** Relocate `configs/` into the package and update all examples.
- **Pros:** Simplifies packaging by putting resources directly in package data.
- **Cons:** Churns established source-tree preset paths and breaks existing examples.
- **Why ruled out:** The existing root `configs/` workflow is useful for editable presets.

### Decision

Option 2 is selected.

The implementation keeps source checkout behavior intact while making installed wheels
self-contained for default/preset configs. The package root becomes the primary library
entry point for wrapper, config, narrator, runtime, tuning, and prompt customization
surfaces, while lower-level helpers remain module-private unless later promoted.

### Pre-Mortem

- Failure mode: root imports become too heavy because they eagerly import optional UI or
  ML dependencies.
  - Mitigation: keep this as a validation point; switch to lazy package-root exports if
    import checks expose unacceptable overhead.
- Failure mode: bundled presets diverge from root `configs/` files.
  - Mitigation: build config resources from the existing root YAML files and keep tests
    covering named preset resolution.
- Failure mode: global prompt customization creates surprising shared state.
  - Mitigation: also support per-instance `VLMNarrator(system_prompt=...)` overrides and
    provide `reset_system_prompt()` for interactive sessions.
- Failure mode: install smoke checks take too long because core dependencies are heavy.
  - Mitigation: run the smoke check manually for this pass and document it for future CI
    consideration.

## Changelog

- 2026-05-08: Created installable-library decision note and implementation-phase log.
- 2026-05-08: Completed Phase 1 packaging metadata: explicit wheel package list,
  sdist includes, forced config preset inclusion under `docugym/configs/`, and
  PEP 561 `py.typed` marker.
- 2026-05-08: Completed Phase 2 config resolution: added preset/path resolver,
  switched `load_settings()` default loading to packaged/source presets, and made
  CLI `--config` plus `list-envs` independent of the caller's current directory.
- 2026-05-08: Completed Phase 4 prompt customization surface: added public prompt
  helpers, moved the built-in system prompt behind that API, and threaded optional
  system prompt overrides through narrator, config, CLI, and wrapper construction.
- 2026-05-08: Completed Phase 3 public API expansion: package-root exports now
  cover wrapper callbacks, settings, narrator, runtime, prompt customization, and
  prompt-tuning entry points for installed-library use.
- 2026-05-08: Updated README and API reference with pip/uv install commands,
  installed-friendly config preset examples, root import guidance, and prompt
  customization examples.
- 2026-05-08: Added regression tests for default/preset config resolution outside
  the repo CWD, CLI preset listing, package-root imports, and prompt override/reset
  behavior.
- 2026-05-08: Refined package-root exports to lazy loading so lightweight imports
  such as `from docugym import load_settings` do not eagerly initialize UI/runtime
  dependencies.
- 2026-05-08: Refined CLI imports to lazy-load display/runtime collaborators so
  installed discovery commands such as `docugym list-envs` avoid pygame startup
  side effects.
- 2026-05-08: Validation passed: Ruff, strict doc-quality, full pytest suite, and
  fresh virtualenv install smoke from `/tmp` covering package-root imports,
  `load_settings()`, `docugym list-envs`, and `docugym show-config`.
- 2026-05-08: Added README status badges for version, supported Python versions,
  passing tests, Ruff lint, strict documentation quality, and install-smoke health.
