---
type: decision
tags: [stage-3, display, readability, subtitle, pygame, layout]
created: 2026-04-24
updated: 2026-04-24
status: active
related: [stage-3-display-layer.md, 2026-04-24-stage-3-display-follow-up-validation-and-text-bands.md]
---

# Stage 3 Display Min Width And Subtitle Width Policy

## Context

Follow-up Ubuntu validation confirmed subtitle and HUD readability, but surfaced a
new usability issue: narrow Atari frame widths made subtitle presentation feel
cramped, while very wide windows can produce subtitle lines that are too long for
comfortable reading. We needed a display policy that improves readability without
distorting environment pixels.

## Research

- Current implementation behavior before this update:
  - Display window width matched scaled env frame width.
  - Narrow envs (for example SpaceInvaders family) therefore produced narrow
    subtitle regions.
  - After text-band adoption, subtitle wrapping still expanded to almost the full
    window width, which can reduce readability on very wide windows.
- Rendering constraints verified from PyGame docs:
  - `pygame.display.set_mode()` creates a display surface with the requested size.
  - `Surface.blit()` positions the source surface at the destination top-left,
    which allows deterministic centering offsets without scaling distortion.
- Validation evidence in this repository:
  - Unit and CLI tests passed after implementation (`21 passed`).
  - Live check completed successfully:
    - `uv run --active docugym display-smoketest --env ALE/SpaceInvaders-v5 --fps 60 --steps 120 --subtitle "Min-width and capped subtitle width check" --min-window-width 960 --subtitle-max-text-width 900`

### Prior Decision Constraint / Conflict

- `stage-3-display-layer.md` accepted overlay-oriented subtitle/HUD behavior as a
  Stage 3 baseline. This policy refines that direction by prioritizing readable
  text layout over strict frame-width coupling for narrow environments.

### Assumptions

- `confident`: Centering narrow frames in a wider window preserves gameplay
  fidelity because no frame resampling is introduced beyond existing scale.
- `confident`: A subtitle wrap-width cap improves line-length readability on very
  wide windows.
- `likely`: A default minimum window width near 960 px is a practical baseline
  for two-line subtitle readability.
- `uncertain`: Optimal minimum/cap values may vary by host DPI and subtitle font.

## Options Considered

### Option 1: Keep frame-coupled width and tune only font size
- **Description:** Keep window width tied to frame width; shrink/grow subtitle font for narrow/wide envs.
- **Pros:** No extra window layout logic.
- **Cons:** Does not address cramped subtitle geometry in narrow windows and introduces font-size instability across envs.

### Option 2: Add minimum window width, center frame, and cap subtitle wrap width
- **Description:** Decouple readable text region from env width by enforcing a minimum window width, centering narrow frames, and limiting subtitle line width.
- **Pros:** Improves readability in both narrow and wide extremes while keeping env pixel geometry intact.
- **Cons:** Adds new layout/config surface area and requires additional tests.

### Option 3: Fixed subtitle panel width independent of window
- **Description:** Keep current window behavior but render subtitle text into a fixed-width panel that may not match window width.
- **Pros:** Strong control over line length.
- **Cons:** Awkward visual composition and inconsistent alignment with HUD/frame regions.

## Decision

Option 2 was selected. It resolves narrow-env subtitle cramping and wide-window
line-length creep at the same time. Compared with Option 1 it addresses geometry,
not just typography. Compared with Option 3 it preserves visual consistency by
keeping all UI elements aligned to a single window layout while allowing explicit
width controls.

## Pre-Mortem

- Defaults may feel too wide or too narrow on some displays.
  Mitigation: expose both values in config and CLI (`min_window_width`,
  `subtitle_max_text_width`) for quick host-specific tuning.
- Centering offsets could regress if future layout code changes.
  Mitigation: keep deterministic helper functions and unit tests for computed
  window size and frame offsets.
- Subtitle cap could be too restrictive for long localized strings.
  Mitigation: preserve two-line wrapping and retain configurable cap value.

## Changelog

- 2026-04-24: Created.
