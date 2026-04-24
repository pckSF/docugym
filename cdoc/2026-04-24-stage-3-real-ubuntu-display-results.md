---
type: log
tags: [stage-3, testing, display, ubuntu, pygame]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-3-display-layer.md]
---

# 2026-04-24 Stage 3 Real Ubuntu Display Results

## Context

Executed the Stage 3 native Ubuntu display-validation checklist from
`stage-3-real-ubuntu-display-testing.md` on Ubuntu 24.04 with the repository
virtual environment active.

## Content

### Commands executed

- `uv run --active pytest -q`
- `uv run --active docugym display-smoketest --env ALE/Breakout-v5 --fps 60 --steps 300`
- `uv run --active docugym display-smoketest --env CartPole-v1 --fps 60 --steps 300`
- `uv run --active docugym display-smoketest --env LunarLander-v3 --fps 60 --steps 300` (optional)

### Outcomes

- Automated checks: `16 passed` in `pytest -q`.
- Required display smoke runs completed for Breakout and CartPole with:
  - SDL/PyGame startup banners present.
  - CLI completion log line confirming `rendered_steps=300`.
  - Terminal summary: `Rendered 300 frame(s) in live display mode`.
- Optional LunarLander run completed with the same successful completion summary.

### Acceptance coverage and gaps

- Covered by execution evidence:
  - Loop completes without runtime errors for required environments.
  - Render loop advances to the requested step budget at target command settings.
- Not directly verified in this non-interactive capture:
  - Human-observed subtitle readability.
  - Human-observed HUD legibility details.
  - Escape key and manual window-close interaction path.
  - Subjective stutter assessment by visual inspection.

## Changelog

- 2026-04-24: Created.
