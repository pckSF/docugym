---
type: log
tags: [stage-3, testing, display, ubuntu, pygame, readability]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-3-display-layer.md, 2026-04-24-stage-3-real-ubuntu-display-results.md]
---

# 2026-04-24 Stage 3 Display Follow-Up Validation And Text Bands

## Context

Follow-up checks were executed after the initial Ubuntu Stage 3 validation log to
close remaining human-observed acceptance points and address subtitle/HUD
occlusion concerns on busy gameplay scenes.

## Content

### Manual acceptance follow-up

- CartPole long-run validation command:
  - `uv run --active docugym display-smoketest --env CartPole-v1 --fps 60 --steps 10000 --subtitle "Acceptance test: subtitle and HUD visibility" --hud`
- Outcome evidence:
  - Completed cleanly with `rendered_steps=2176`, consistent with interactive
    Escape termination before max-step limit.
  - Reported manual observations: visible live window, readable subtitle,
    readable HUD fields, and clean close behavior.

### Noisy-background readability check

- SpaceInvaders validation command:
  - `uv run --active docugym display-smoketest --env ALE/SpaceInvaders-v5 --fps 60 --steps 10000 --subtitle "Subtitle readability check on noisy background" --hud`
- Outcome evidence:
  - Completed cleanly with `rendered_steps=7716`, again consistent with
    interactive early termination.
  - Remaining UX issue identified: subtitle/HUD readability was acceptable, but
    drawing text directly over gameplay pixels was distracting.

### Mitigation implemented in same follow-up cycle

- Added dedicated text-band rendering mode in the display layer so HUD and
  subtitle can render outside gameplay pixels.
- Exposed mode control as CLI flag `--text-bands/--overlay-text` and config
  field `display.text_bands`.
- Set repository default to `display.text_bands: true`.
- Regression status after implementation: `17 passed` in `pytest -q`.

## Changelog

- 2026-04-24: Created.
