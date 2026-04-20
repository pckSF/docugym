from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import typer

from docugym.config import AppSettings, load_settings
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
