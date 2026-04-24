from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Literal

import typer

from docugym.config import AppSettings, load_settings
from docugym.display import run_display_smoketest
from docugym.env import run_smoketest
from docugym.logging_config import configure_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="DocuGym CLI for local narrated Gymnasium runs.",
)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppState:
    """Shared CLI runtime state."""

    settings: AppSettings
    config_path: Path


def _get_state(ctx: typer.Context) -> AppState:
    if not isinstance(ctx.obj, AppState):
        raise typer.BadParameter("Application state is not initialized.")
    return ctx.obj


def _parse_env_kwargs(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("--env-kwargs must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise typer.BadParameter("--env-kwargs must decode to a JSON object")

    return dict(parsed)


@app.callback()
def main(
    ctx: typer.Context,
    config: Path = typer.Option(
        Path("configs/default.yaml"),
        "--config",
        "-c",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to YAML configuration file.",
    ),
    log_level: str = typer.Option("INFO", help="Python logging level."),
) -> None:
    """Initialize application configuration and logging."""

    configure_logging(log_level)
    settings = load_settings(config)
    ctx.obj = AppState(settings=settings, config_path=config)
    logger.debug("Loaded configuration from %s", config)


@app.command("show-config")
def show_config(ctx: typer.Context) -> None:
    """Print the effective configuration as pretty JSON."""

    settings = _get_state(ctx).settings
    typer.echo(json.dumps(settings.model_dump(mode="json"), indent=2))


@app.command("smoketest")
def smoketest(
    ctx: typer.Context,
    env: str | None = typer.Option(None, "--env", help="Gymnasium environment id."),
    steps: int = typer.Option(200, min=1, help="Number of frames to capture."),
    seed: int | None = typer.Option(None, help="Random seed for reset/action space."),
    out_dir: Path = typer.Option(
        Path("out/frames"),
        "--out-dir",
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Directory where rendered PNG frames are written.",
    ),
    agent: Literal["random", "scripted", "sb3"] = typer.Option(
        "random",
        "--agent",
        help="Action source used during smoke run.",
    ),
    repo_id: str | None = typer.Option(
        None,
        "--repo-id",
        help="Hugging Face model repository id for SB3 policy loading.",
    ),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help="Policy file name inside the SB3 Hugging Face repo.",
    ),
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Run a local Stage 2 smoke test and persist rendered frames to disk."""

    state = _get_state(ctx)
    config = state.settings

    env_id = env or config.run.env_id
    effective_seed = config.run.seed if seed is None else seed
    effective_repo_id = repo_id or config.agent.sb3_repo_id
    effective_filename = filename or config.agent.sb3_filename

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    frame_paths = run_smoketest(
        env_id=env_id,
        seed=effective_seed,
        steps=steps,
        out_dir=out_dir,
        env_kwargs=effective_env_kwargs,
        agent_kind=agent,
        sb3_repo_id=effective_repo_id,
        sb3_filename=effective_filename,
    )

    logger.info(
        "Smoketest complete: env=%s steps=%d frames=%d out_dir=%s",
        env_id,
        steps,
        len(frame_paths),
        out_dir,
    )
    typer.echo(f"Saved {len(frame_paths)} frame(s) to {out_dir}")


@app.command("display-smoketest")
def display_smoketest(
    ctx: typer.Context,
    env: str | None = typer.Option(None, "--env", help="Gymnasium environment id."),
    seed: int | None = typer.Option(None, help="Random seed for reset/action space."),
    fps: int | None = typer.Option(None, min=1, help="Target display FPS."),
    window_scale: int | None = typer.Option(
        None,
        min=1,
        help="Integer multiplier applied to raw env frame size.",
    ),
    min_window_width: int | None = typer.Option(
        None,
        min=1,
        help="Minimum window width in pixels; narrower env frames are centered.",
    ),
    steps: int | None = typer.Option(
        None,
        min=1,
        help="Optional max number of displayed steps before exiting.",
    ),
    subtitle: str = typer.Option(
        "In this pixelated arena, every ricochet tells a survival story.",
        help="Subtitle text rendered over gameplay during Stage 3 display testing.",
    ),
    hud: bool | None = typer.Option(
        None,
        "--hud/--no-hud",
        help="Enable or disable HUD status bar overlay.",
    ),
    text_bands: bool | None = typer.Option(
        None,
        "--text-bands/--overlay-text",
        help=(
            "Render HUD/subtitle in dedicated top and bottom bands instead "
            "of overlaying gameplay pixels."
        ),
    ),
    subtitle_max_text_width: int | None = typer.Option(
        None,
        min=1,
        help="Maximum subtitle wrapping width in pixels, even on very wide windows.",
    ),
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Run the Stage 3 live display loop with a random agent."""

    state = _get_state(ctx)
    config = state.settings

    env_id = env or config.run.env_id
    effective_seed = config.run.seed if seed is None else seed
    effective_fps = config.run.fps if fps is None else fps
    effective_window_scale = (
        config.display.window_scale if window_scale is None else window_scale
    )
    effective_min_window_width = (
        config.display.min_window_width
        if min_window_width is None
        else min_window_width
    )
    effective_hud = config.display.hud if hud is None else hud
    effective_text_bands = (
        config.display.text_bands if text_bands is None else text_bands
    )
    effective_subtitle_max_text_width = (
        config.display.subtitle_max_text_width
        if subtitle_max_text_width is None
        else subtitle_max_text_width
    )

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    rendered_steps = run_display_smoketest(
        env_id=env_id,
        seed=effective_seed,
        fps=effective_fps,
        window_scale=effective_window_scale,
        min_window_width=effective_min_window_width,
        subtitle=subtitle,
        subtitle_font=config.display.subtitle_font,
        subtitle_size=config.display.subtitle_size,
        subtitle_max_text_width=effective_subtitle_max_text_width,
        hud=effective_hud,
        text_bands=effective_text_bands,
        env_kwargs=effective_env_kwargs,
        max_steps=steps,
    )

    logger.info(
        "Display smoketest complete: env=%s rendered_steps=%d fps=%d scale=%d",
        env_id,
        rendered_steps,
        effective_fps,
        effective_window_scale,
    )
    typer.echo(f"Rendered {rendered_steps} frame(s) in live display mode")
