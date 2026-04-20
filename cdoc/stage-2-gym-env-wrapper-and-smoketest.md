---
type: decision
tags: [stage-2, env, gymnasium, sb3, smoketest]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [stage-1-scaffolding-and-config-loader.md]
---

# Stage 2 Gym Environment Wrapper and Smoketest

## Context

Stage 2 in `specification.md` requires an environment wrapper module, baseline
agents, SB3 policy loading from Hugging Face, and a smoke-test command that
writes rendered frames. Stage 1 already established package scaffolding and
typed configuration, so Stage 2 should attach to existing CLI/config patterns
without introducing blocking dependencies in unrelated tests.

## Research

- Current repo state before this update had no `docugym/env.py` module and no
  smoke-test command in the CLI.
- Existing default config includes Atari-specific env kwargs (`frameskip`,
  `repeat_action_probability`) that are invalid for many non-Atari envs.
- Gymnasium docs confirm `gym.make(..., render_mode="rgb_array")` is the
  supported path for frame extraction.
- ALE docs confirm Atari envs should call `gym.register_envs(ale_py)` before
  `gym.make("ALE/..." )`.
- `huggingface_sb3.load_from_hub(repo_id, filename)` returns a downloaded file
  path but does not expose a custom cache-dir parameter.
- Legacy SB3 Hub checkpoints (for example `sb3/ppo-LunarLander-v2`) may still
  serialize OpenAI Gym-space metadata and require compatibility packages (`gym`,
  `shimmy`) at load time.
- Practical runtime checks in this workspace confirmed:
  - Classic control, Box2D, and Atari envs all produced non-black RGB frames.
  - CLI smoke-test flow wrote frames successfully for Atari and SB3-driven
    LunarLander runs.
  - SB3 policy loading works, with expected warnings tied to legacy checkpoint
    serialization.

### Assumptions

- `likely`: Keeping SB3 load warnings (legacy checkpoint metadata) is acceptable
  for Stage 2 as long as load + inference succeed.
- `confident`: Copying policy files into `~/.cache/docugym/policies/` gives a
  predictable cache location while still using `load_from_hub`.
- `likely`: Stage 2 smoke tests should prioritize deterministic file output and
  compatibility checks rather than gameplay quality.
- `uncertain`: Future newer Hub checkpoints may let us remove `gym` compatibility
  dependencies entirely.

## Options Considered

### Option 1: Thin wrapper only, no integrated smoke pipeline
- **Description:** Implement `make_env` and agents, but keep smoke logic ad-hoc in CLI.
- **Pros:** Minimal initial code surface.
- **Cons:** Duplicates frame export logic, weak testability, harder evolution into
  Stage 6 pipeline components.

### Option 2: Dedicated environment module with runner + policy cache + CLI command
- **Description:** Implement `docugym/env.py` with `make_env`, agents, policy loader,
  and `run_smoketest`; wire a single CLI `smoketest` entrypoint.
- **Pros:** Cohesive Stage 2 boundary, easy unit testing, direct reuse in later
  orchestration stages.
- **Cons:** Requires adding several runtime dependencies and compatibility handling
  for older checkpoints.

### Option 3: Full integration-first implementation targeting Stage 6 queue model
- **Description:** Skip a simple smoke runner and jump to asynchronous pipeline
  primitives immediately.
- **Pros:** Might reduce later refactor work.
- **Cons:** Over-scoped for Stage 2 and increases failure/debug surface before
  baseline env and policy loading are stable.

## Decision

Option 2 was selected. It preserves Stage 2 scope while creating reusable code
boundaries for later stages. Compared with Option 1, it avoids scattering core
env/policy behavior across CLI glue. Compared with Option 3, it keeps complexity
aligned with current requirements and validates rendering/policy compatibility
before async pipeline work.

## Pre-Mortem

- Incompatible env kwargs could break smoke runs when users override env ids.
  Mitigation: only inherit config env kwargs when using the configured env id,
  and allow explicit CLI kwargs override.
- Old Hub checkpoints can fail to deserialize without compatibility modules.
  Mitigation: include `gym` and `shimmy` dependencies and keep loading logic
  explicit.
- Optional dependency drift between `pyproject.toml` and `requirements.txt`
  could break devcontainer onboarding.
  Mitigation: update both files in the same change and refresh lockfile.
- Stage 2 tests could become flaky if they rely on heavyweight external env
  runtime in CI.
  Mitigation: keep core tests mocked/unit-level and perform runtime smoke checks
  as command validation.

## Changelog

- 2026-04-20: Created.
