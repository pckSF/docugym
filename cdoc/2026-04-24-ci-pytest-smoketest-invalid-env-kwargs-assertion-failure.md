---
type: log
tags: [ci, pytest, stage-2, cli, validation]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-2-gym-env-wrapper-and-smoketest.md]
---

# 2026-04-24 CI Pytest Smoketest Invalid Env Kwargs Assertion Failure

## Context

GitHub Actions execution of `uv run pytest -q` failed after a Stage 3 follow-up
cycle, while most tests still passed.

## Content

### Observed CI result

- Command: `uv run pytest -q`
- Outcome: `1 failed, 20 passed, 1 warning`.
- Failing test: `tests/test_cli.py::test_smoketest_rejects_invalid_env_kwargs`.

### Failure details

- Assertion expected `"--env-kwargs must be valid JSON"` in CLI output.
- Captured output primarily contained Typer/Click usage and styled error text,
  and the exact plain substring assertion did not match.
- Exit behavior remained non-zero (`SystemExit(2)`), so argument validation did
  still reject invalid JSON input.

### Implication

- The failure indicates a brittle output-string assertion against formatted CLI
  diagnostics, not a confirmed regression in invalid-JSON rejection behavior.

### Resolution applied

- Patched `tests/test_cli.py::test_smoketest_rejects_invalid_env_kwargs` to
  normalize ANSI escape sequences before asserting on error semantics.
- Replaced exact raw-substring matching with stable checks for
  `env-kwargs` and `valid JSON` in normalized output.
- Verification after patch: `uv run pytest -q` passed (`21 passed, 1 warning`).

## Changelog

- 2026-04-24: Created.
- 2026-04-24: Added implemented test hardening details and full-suite verification outcome.
