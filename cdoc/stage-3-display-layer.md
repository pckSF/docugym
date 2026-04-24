---
type: decision
tags: [stage-3, display, pygame, ui]
created: 2026-04-20
updated: 2026-04-24
status: active
related: [stage-2-gym-env-wrapper-and-smoketest.md, 2026-04-24-stage-3-real-ubuntu-display-results.md, 2026-04-24-stage-3-display-follow-up-validation-and-text-bands.md, stage-3-display-min-width-and-subtitle-width-policy.md, networking-ports-and-services.md]
---

# Stage 3 Display Layer

## Context

Stage 3 in specification.md requires a PyGame display layer that renders live
Gymnasium frames with FPS pacing, subtitle overlay, and a status bar containing
environment id, step count, and episode reward. This work also needs a runnable
CLI path so Stage 3 can be exercised independently from later narration/audio
stages.

## Research

- Existing implementation state before this update:
  - Stage 2 already provided `make_env` and `RandomAgent` in `docugym/env.py`.
  - CLI had only `smoketest` (PNG export), with no live display loop.
  - Display settings (`window_scale`, subtitle font/size, HUD toggle) were
    already present in `configs/default.yaml` and `docugym/config.py`.
- PyGame documentation constraints and guidance:
  - `pygame.display.set_mode()` creates the single active display surface.
  - Frame updates require `pygame.display.flip()` (or `update()`) after blits.
  - `pygame.time.Clock.tick(fps)` is the standard pacing mechanism for an FPS cap.
  - `pygame.surfarray.make_surface()` expects array orientation indexed by X then Y,
    so Gym frames (`H, W, C`) need transposition to (`W, H, C`) before blitting.
- Testing and toolchain findings in this repository:
  - Headless-friendly unit tests should not depend on opening a real SDL window,
    so Stage 3 loop logic was tested with a mocked display object.
  - Pre-commit revealed a pre-existing static-type issue in config source loading;
    it was fixed while implementing Stage 3 to keep hooks green.

### Assumptions

- `confident`: A dedicated `display-smoketest` CLI command is the right Stage 3
  entrypoint because Stage 4+ orchestration has not been implemented yet.
- `likely`: `window_scale` is sufficient for Stage 3 "configurable window size"
  requirements; explicit width/height controls can be deferred.
- `likely`: A hardcoded subtitle string in CLI options satisfies the Stage 3 stub
  subtitle requirement.
- `uncertain`: Live 60 FPS behavior for Atari (`ALE/Breakout-v5`) depends on host
  graphics stack and SDL backend availability, which CI does not fully represent.

## Options Considered

### Option 1: Add display rendering directly inside CLI command logic
- **Description:** Keep all Stage 3 window/event/render code in `docugym/cli.py`.
- **Pros:** Fewer files and quick implementation.
- **Cons:** Poor separation of concerns, difficult unit testing, and harder reuse
  in Stage 6 async orchestration.

### Option 2: Create `docugym/display.py` with `Display` class + Stage 3 runner
- **Description:** Encapsulate PyGame concerns in a dedicated class and expose a
  `run_display_smoketest` function used by CLI.
- **Pros:** Matches specification structure, isolates UI behavior, enables testable
  orchestration around mocked display objects, and keeps CLI thin.
- **Cons:** Slightly larger upfront code surface.

### Option 3: Use Gymnasium native human render path instead of explicit PyGame UI
- **Description:** Depend on environment-provided human rendering for display and
  avoid custom overlay rendering.
- **Pros:** Lower custom rendering code.
- **Cons:** Weak control over subtitle/HUD overlays and inconsistent behavior across
  env families, making Stage 3 DoD less reliable.

## Decision

Option 2 was selected. It satisfies Stage 3 requirements with clean module
boundaries and avoids coupling display internals to CLI argument parsing.
Compared with Option 1, it is easier to validate and evolve. Compared with
Option 3, it provides deterministic control over subtitle and status-bar
rendering needed for later narration integration.

## Pre-Mortem

- Frame conversion or transposition bugs may produce swapped axes or distorted
  colors.
  Mitigation: validate frame shape/channels and normalize to contiguous uint8
  RGB before surfarray conversion.
- Headless/runtime SDL differences may hide window-specific issues in CI.
  Mitigation: keep loop tests display-mocked and perform manual live smoke checks
  in a GPU-capable desktop/devcontainer session.
- Overlay text may become unreadable on bright frames.
  Mitigation: render subtitles/HUD over semi-transparent dark cards and cap
  subtitle lines to avoid overflow.
- Stage 4+ integration could require event-loop ownership changes.
  Mitigation: keep `Display` responsibilities narrow (render + pacing + events)
  and keep environment stepping in a separate runner function.

## Changelog

- 2026-04-20: Created.
- 2026-04-20: Linked temporary open task for real-Ubuntu manual display validation.
- 2026-04-20: Linked networking reference note for active and planned service ports.
- 2026-04-24: Linked native Ubuntu Stage 3 validation results log and closed temporary open task tracking.
- 2026-04-24: Linked follow-up Ubuntu validation and text-band readability mitigation log.
- 2026-04-24: Linked minimum-width and subtitle-width decision note for narrow/wide env readability balancing.
