---
type: open_task
tags: [stage-3, testing, display, ubuntu]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [stage-3-display-layer.md]
---

# Stage 3 Real Ubuntu Display Testing

## Context

Stage 3 display logic passes unit tests and offscreen smoke tests in the current
devcontainer, but SDL is still using an offscreen backend there. We need one
manual validation pass on a real Ubuntu desktop session to verify visible-window
behavior, event handling, and practical frame pacing.

## Content

### Where to run

- Native Ubuntu desktop session (not inside the current WSL Docker path).
- GPU-accelerated local session with a normal compositor (Wayland or X11).

### How to run

1. Clone the repository on the Ubuntu host and enter the project root.
2. Create and activate a user-level environment:
   - `uv venv --python 3.12 ~/.venv`
   - `source ~/.venv/bin/activate`
3. Install dependencies from the repository:
   - `uv pip install -r requirements.txt`
4. Run automated checks before manual UI validation:
   - `uv run --active pytest -q`
5. Run manual display smoke tests:
   - `uv run --active docugym display-smoketest --env ALE/Breakout-v5 --fps 60 --steps 300`
   - `uv run --active docugym display-smoketest --env CartPole-v1 --fps 60 --steps 300`
   - Optional: `uv run --active docugym display-smoketest --env LunarLander-v3 --fps 60 --steps 300`
6. Validate acceptance points during each run:
   - A visible window opens and updates continuously.
   - Subtitle text is visible and readable.
   - HUD status bar shows env id, step count, and episode reward.
   - Escape key and window close event terminate cleanly.
   - No obvious stutter beyond expected env/model overhead.

### Completion and deletion rule

Delete this note once all required manual checks above are complete and results
have been recorded in a durable note (for example a date-prefixed `log` note)
with a brief outcome summary linked from `stage-3-display-layer.md`.

## Changelog

- 2026-04-20: Created.
