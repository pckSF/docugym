"""Typer-powered CLI for smoke tests, live runs, and prompt-tuning workflows.

Command handlers merge CLI overrides with YAML defaults so the same runtime
configuration model can be used interactively and in scripted environments.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
import yaml

from docugym.config import AppSettings, load_settings
from docugym.config_files import (
    ConfigNotFoundError,
    RUNTIME_CONFIG_PRESET_NAMES,
    resolved_config_path,
)
from docugym.env import _is_trusted_repo, _normalize_repo_prefixes
from docugym.logging_config import configure_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="DocuGym CLI for local narrated Gymnasium runs.",
)
tune_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Narration tuning helpers.",
)
app.add_typer(tune_app, name="tune")
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

run_display_smoketest: Any | None = None
run_prompt_tuning: Any | None = None
run_session_sync: Any | None = None
run_smoketest: Any | None = None
VLMNarrator: Any | None = None

_KOKORO_BRITISH_VOICE_SAMPLES: tuple[tuple[str, str], ...] = (
    (
        "bm_george",
        'Sample: "With patient calm, the explorer weighs its next move."',
    ),
    (
        "bm_fable",
        'Sample: "A brief hush, then the hunt resumes in measured rhythm."',
    ),
    (
        "bm_lewis",
        'Sample: "Across uncertain ground, instinct and timing decide survival."',
    ),
    (
        "bm_daniel",
        'Sample: "The pace softens, as if the world itself is listening."',
    ),
    (
        "bf_alice",
        'Sample: "At the boundary of danger, composure is everything."',
    ),
    (
        "bf_emma",
        'Sample: "A graceful turn reveals the creature\'s quiet intent."',
    ),
    (
        "bf_isabella",
        'Sample: "In this fragile interval, each motion carries consequence."',
    ),
    (
        "bf_lily",
        'Sample: "One careful adjustment, and balance returns to the scene."',
    ),
)


def _load_cli_dependency(name: str, module_name: str) -> Any:
    """Resolve a heavy CLI collaborator only when a command needs it.

    Args:
        name: Module-level dependency name used by command handlers and tests.
        module_name: Import path containing the concrete dependency.

    Returns:
        Dependency object, using a monkeypatched module global when present.
    """

    dependency = globals()[name]
    if dependency is not None:
        return dependency
    return getattr(import_module(module_name), name)


@dataclass(slots=True)
class AppState:
    """Shared CLI runtime state passed through Typer context.

    Attributes:
        settings: Effective application settings after source merging.
        config_ref: Preset name or configuration file path used to build
            ``settings``.
    """

    settings: AppSettings
    config_ref: str


def _get_state(ctx: typer.Context) -> AppState:
    """Return initialized CLI state or fail with a user-facing error.

    Args:
        ctx: Typer context that stores shared command state.

    Returns:
        Shared application state initialized by the root callback.

    Raises:
        typer.BadParameter: If the callback did not initialize ``ctx.obj``.
    """

    if not isinstance(ctx.obj, AppState):
        raise typer.BadParameter("Application state is not initialized.")
    return ctx.obj


def _parse_env_kwargs(value: str | None) -> dict[str, Any]:
    """Parse ``--env-kwargs`` JSON into ``gym.make`` kwargs.

    The option must decode to a JSON object so downstream env creation receives a
    mapping, not list/primitive values.
    """

    if value is None:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("--env-kwargs must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise typer.BadParameter("--env-kwargs must decode to a JSON object")

    return dict(parsed)


def _resolve_trusted_repo_enforcement(
    *,
    agent_kind: Literal["random", "scripted", "sb3"],
    repo_id: str,
    revision: str | None,
    trusted_repo_prefixes: Sequence[str],
    enforce_trusted_repo: bool,
    allow_untrusted_repo: bool,
    yes: bool,
) -> bool:
    """Resolve effective trust enforcement for one CLI command invocation.

    Args:
        agent_kind: Effective CLI agent selection.
        repo_id: Effective SB3 repository id.
        revision: Effective SB3 revision pin.
        trusted_repo_prefixes: Configured trusted repository prefixes.
        enforce_trusted_repo: Config-level trust enforcement toggle.
        allow_untrusted_repo: CLI opt-in to untrusted SB3 loading.
        yes: Skip interactive confirmation when opting into untrusted loading.

    Returns:
        Effective ``enforce_trusted_repo`` value to pass downstream.

    Raises:
        typer.BadParameter: If explicit untrusted opt-in is missing or if a
            custom untrusted repo has no revision pin.
        typer.Exit: If interactive confirmation is declined.
    """

    if agent_kind != "sb3":
        return enforce_trusted_repo

    trusted_prefixes = _normalize_repo_prefixes(trusted_repo_prefixes)
    repo_is_trusted = _is_trusted_repo(repo_id, trusted_prefixes)

    if not repo_is_trusted and revision is None:
        raise typer.BadParameter(
            "Custom SB3 repositories must pin --revision (or agent.sb3_revision) "
            "before policy loading.",
            param_hint="--revision",
        )

    requires_explicit_opt_in = (not enforce_trusted_repo) or (not repo_is_trusted)
    if not requires_explicit_opt_in:
        return enforce_trusted_repo

    if not allow_untrusted_repo:
        raise typer.BadParameter(
            "SB3 policy loading with untrusted settings requires "
            "--allow-untrusted-repo. Stable-Baselines3 deserialization can "
            "execute arbitrary code.",
            param_hint="--allow-untrusted-repo",
        )

    if not yes:
        confirmed = typer.confirm(
            "You are opting into untrusted SB3 policy deserialization. Continue?",
            default=False,
        )
        if not confirmed:
            raise typer.Exit(code=1)

    # Returning False preserves the warning-only loader path only when explicitly
    # acknowledged by the operator for this invocation.
    return False


def _load_preset_settings(config_path: Path) -> AppSettings:
    """Load one preset YAML file into validated application settings.

    Args:
        config_path: Path to a YAML preset file under ``configs/``.

    Returns:
        Validated settings object decoded from the preset file.

    Raises:
        ValueError: If YAML content is not a mapping at the root.
    """

    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw_data is None:
        raw_data = {}
    if not isinstance(raw_data, dict):
        raise ValueError("Preset config must decode to a YAML mapping")
    return AppSettings.model_validate(raw_data)


@app.callback()
def main(
    ctx: typer.Context,
    config: str = typer.Option(
        "default",
        "--config",
        "-c",
        help="YAML config path or packaged preset name.",
    ),
    log_level: str = typer.Option("INFO", help="Python logging level."),
) -> None:
    """Initialize CLI process state before any subcommand executes.

    The callback configures logging and stores validated settings in ``ctx.obj`` so
    subcommands can share one consistent configuration source.

    Args:
        ctx: Typer context used to store shared application state.
        config: YAML file path or packaged preset name used to populate
            ``AppSettings``.
        log_level: Logging verbosity passed to runtime logger configuration.

    Raises:
        typer.BadParameter: If ``config`` is neither a known preset nor an
            existing YAML file.
    """

    configure_logging(log_level)
    try:
        settings = load_settings(config)
    except ConfigNotFoundError as exc:
        raise typer.BadParameter(str(exc), param_hint="--config") from exc

    ctx.obj = AppState(settings=settings, config_ref=config)
    logger.debug("Loaded configuration from %s", config)


@app.command("show-config")
def show_config(ctx: typer.Context) -> None:
    """Print effective configuration as formatted JSON.

    Args:
        ctx: Typer context carrying shared application state.

    Returns:
        ``None``. Writes formatted JSON to stdout.
    """

    settings = _get_state(ctx).settings
    typer.echo(json.dumps(settings.model_dump(mode="json"), indent=2))


@app.command("list-voices")
def list_voices() -> None:
    """Print curated Kokoro British voice ids with sample phrases.

    This command is a quick discovery surface for choosing ``--tts-voice`` values.

    Returns:
        ``None``. Prints voice ids and sample text lines.
    """

    typer.echo("Kokoro British voices:")
    for voice_id, sample in _KOKORO_BRITISH_VOICE_SAMPLES:
        typer.echo(f"- {voice_id}: {sample}")


@app.command("list-envs")
def list_envs() -> None:
    """List packaged presets with resolved env id, agent kind, and policy hint.

    Presets are loaded through the same settings model used by runtime commands so
    this output mirrors effective default behavior.

    Returns:
        ``None``. Prints one line per discovered preset.
    """

    typer.echo("Supported env presets:")

    for preset_name in RUNTIME_CONFIG_PRESET_NAMES:
        with resolved_config_path(preset_name) as preset_path:
            settings = _load_preset_settings(preset_path)
        policy = settings.agent.sb3_repo_id if settings.agent.kind == "sb3" else "n/a"
        typer.echo(
            "- "
            f"{preset_name}: env={settings.run.env_id} "
            f"agent={settings.agent.kind} policy={policy}"
        )


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
        help=(
            "Hugging Face model repository id for SB3 policy loading. "
            "Only trusted repos should be used because SB3 deserialization can "
            "execute arbitrary code."
        ),
    ),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help="Policy file name inside the SB3 Hugging Face repo.",
    ),
    revision: str | None = typer.Option(
        None,
        "--revision",
        help="Optional Hugging Face commit SHA, tag, or branch for SB3 download.",
    ),
    allow_untrusted_repo: bool = typer.Option(
        False,
        "--allow-untrusted-repo",
        help=(
            "Allow SB3 policy loading when trust enforcement is disabled or the "
            "repo id is outside trusted prefixes."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip the interactive untrusted-repo confirmation prompt.",
    ),
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Capture a short rendered-frame sequence for setup verification.

    CLI-provided values override config defaults, while ``--env-kwargs`` are merged
    on top of config-provided env kwargs for the selected environment.

    Args:
        ctx: Typer context carrying shared settings.

    Raises:
        typer.BadParameter: If ``--env-kwargs`` is not valid JSON object input.
    """

    state = _get_state(ctx)
    config = state.settings

    env_id = env or config.run.env_id
    effective_seed = config.run.seed if seed is None else seed
    effective_repo_id = repo_id or config.agent.sb3_repo_id
    effective_filename = filename or config.agent.sb3_filename
    effective_revision = revision
    if effective_revision is None and repo_id is None:
        effective_revision = config.agent.sb3_revision
    effective_enforce_trusted_repo = _resolve_trusted_repo_enforcement(
        agent_kind=agent,
        repo_id=effective_repo_id,
        revision=effective_revision,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
        allow_untrusted_repo=allow_untrusted_repo,
        yes=yes,
    )

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    smoke_runner = _load_cli_dependency("run_smoketest", "docugym.env")
    frame_paths = smoke_runner(
        env_id=env_id,
        seed=effective_seed,
        steps=steps,
        out_dir=out_dir,
        env_kwargs=effective_env_kwargs,
        agent_kind=agent,
        sb3_repo_id=effective_repo_id,
        sb3_filename=effective_filename,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=effective_enforce_trusted_repo,
        sb3_revision=effective_revision,
        sb3_algorithm=config.agent.sb3_algorithm,
        sb3_device=config.agent.device,
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
        help="Subtitle text rendered over gameplay during live display testing.",
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
    """Run display-only smoke validation with merged config and CLI overrides.

    This command intentionally excludes narration/TTS so display layout, FPS pacing,
    and keyboard controls can be verified independently.

    Args:
        ctx: Typer context carrying shared settings.

    Raises:
        typer.BadParameter: If ``--env-kwargs`` is not valid JSON object input.
    """

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

    display_smoke_runner = _load_cli_dependency(
        "run_display_smoketest",
        "docugym.display",
    )
    rendered_steps = display_smoke_runner(
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


@app.command("run")
def run(
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
    subtitle_max_text_width: int | None = typer.Option(
        None,
        min=1,
        help="Maximum subtitle wrapping width in pixels, even on very wide windows.",
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
    steps: int | None = typer.Option(
        None,
        "--steps",
        min=1,
        help="Optional max number of rendered steps before exiting.",
    ),
    narrate_every: int | None = typer.Option(
        None,
        min=1,
        help=(
            "Override fixed narration cadence in frames. When omitted, "
            "config narration.interval_seconds is used."
        ),
    ),
    agent: Literal["random", "scripted", "sb3"] | None = typer.Option(
        None,
        "--agent",
        help="Action source used during run.",
    ),
    policy: str | None = typer.Option(
        None,
        "--policy",
        help=(
            "SB3 policy repo shorthand (e.g. sb3/ppo-PongNoFrameskip-v4). "
            "Sets --agent sb3. Do not load untrusted policies because SB3 "
            "deserialization can execute arbitrary code."
        ),
    ),
    repo_id: str | None = typer.Option(
        None,
        "--repo-id",
        help="Hugging Face model repository id for SB3 policy loading.",
    ),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help=(
            "Policy filename inside the SB3 Hugging Face repo. "
            "Use only trusted model artifacts."
        ),
    ),
    revision: str | None = typer.Option(
        None,
        "--revision",
        help="Optional Hugging Face commit SHA, tag, or branch for SB3 download.",
    ),
    allow_untrusted_repo: bool = typer.Option(
        False,
        "--allow-untrusted-repo",
        help=(
            "Allow SB3 policy loading when trust enforcement is disabled or the "
            "repo id is outside trusted prefixes."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip the interactive untrusted-repo confirmation prompt.",
    ),
    voice: bool | None = typer.Option(
        None,
        "--voice/--no-voice",
        help=(
            "Enable spoken narration audio. Use --no-voice for subtitle-only "
            "narration mode."
        ),
    ),
    record: Path | None = typer.Option(
        None,
        "--record",
        help=(
            "Optional MP4 output path for live session recording. "
            "When omitted, config recording.enabled/out_path is used."
        ),
    ),
    wait_for_vlm: bool = typer.Option(
        False,
        "--wait-for-vlm",
        help="Poll /models until the local VLM endpoint is ready.",
    ),
    wait_timeout: float = typer.Option(
        60.0,
        "--wait-timeout",
        min=1.0,
        help="Maximum seconds to wait when --wait-for-vlm is enabled.",
    ),
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Run the full narrated session pipeline from CLI configuration.

    This command is the primary local entrypoint: it resolves effective options,
    optionally waits for the VLM endpoint, then executes the async runtime through
    its synchronous wrapper.

    Args:
        ctx: Typer context carrying shared settings.

    Raises:
        typer.Exit: If ``--wait-for-vlm`` is enabled and readiness times out.
        typer.BadParameter: If ``--env-kwargs`` is not valid JSON object input.
    """

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
    effective_subtitle_max_text_width = (
        config.display.subtitle_max_text_width
        if subtitle_max_text_width is None
        else subtitle_max_text_width
    )
    effective_hud = config.display.hud if hud is None else hud
    effective_text_bands = (
        config.display.text_bands if text_bands is None else text_bands
    )
    effective_voice = config.tts.enabled if voice is None else voice
    effective_record_out_path: Path | None = None
    if record is not None:
        effective_record_out_path = record
    elif config.recording.enabled:
        effective_record_out_path = Path(config.recording.out_path)

    effective_interval_seconds = config.narration.interval_seconds
    if narrate_every is not None:
        effective_interval_seconds = narrate_every / float(effective_fps)

    effective_agent = config.agent.kind if agent is None else agent
    effective_repo_id = repo_id or config.agent.sb3_repo_id
    effective_filename = filename or config.agent.sb3_filename
    effective_revision = revision
    if effective_revision is None and repo_id is None and policy is None:
        effective_revision = config.agent.sb3_revision
    if policy:
        effective_agent = "sb3"
        effective_repo_id = policy
        if filename is None:
            effective_filename = f"{policy.rsplit('/', maxsplit=1)[-1]}.zip"
    effective_enforce_trusted_repo = _resolve_trusted_repo_enforcement(
        agent_kind=effective_agent,
        repo_id=effective_repo_id,
        revision=effective_revision,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
        allow_untrusted_repo=allow_untrusted_repo,
        yes=yes,
    )

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    narrator_class = _load_cli_dependency("VLMNarrator", "docugym.narrator")
    narrator = narrator_class(
        base_url=config.vlm.base_url,
        model=config.vlm.model,
        max_tokens=config.vlm.max_tokens,
        temperature=config.vlm.temperature,
        top_p=config.vlm.top_p,
        image_detail=config.vlm.image_detail,
        system_prompt=config.narration.system_prompt,
    )

    if wait_for_vlm:
        typer.echo(
            f"Waiting for VLM endpoint at {config.vlm.base_url} "
            f"(timeout {wait_timeout:.1f}s)..."
        )
        ready = narrator.wait_until_ready_sync(timeout_seconds=wait_timeout)
        if not ready:
            typer.secho(
                "VLM endpoint did not become ready before timeout. "
                "Start the sidecar and retry.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    session_runner = _load_cli_dependency("run_session_sync", "docugym.runtime")
    result = session_runner(
        env_id=env_id,
        seed=effective_seed,
        fps=effective_fps,
        window_scale=effective_window_scale,
        subtitle_font=config.display.subtitle_font,
        subtitle_size=config.display.subtitle_size,
        subtitle_max_text_width=effective_subtitle_max_text_width,
        hud=effective_hud,
        text_bands=effective_text_bands,
        min_window_width=effective_min_window_width,
        env_kwargs=effective_env_kwargs,
        narrator=narrator,
        narration_interval_seconds=effective_interval_seconds,
        min_gap_seconds=config.narration.min_gap_seconds,
        reward_spike_threshold=config.narration.reward_spike_threshold,
        pixel_delta_threshold=config.narration.pixel_delta_threshold,
        max_context_events=config.narration.max_context_events,
        previous_narration_window=config.narration.previous_narration_window,
        agent_kind=effective_agent,
        sb3_repo_id=effective_repo_id,
        sb3_filename=effective_filename,
        sb3_algorithm=config.agent.sb3_algorithm,
        sb3_device=config.agent.device,
        sb3_revision=effective_revision,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=effective_enforce_trusted_repo,
        voice_enabled=effective_voice,
        tts_engine=config.tts.engine,
        tts_voice=config.tts.kokoro.voice,
        tts_speed=config.tts.kokoro.speed,
        tts_sample_rate=config.tts.kokoro.sample_rate,
        record_out_path=effective_record_out_path,
        max_steps=steps,
        max_episodes=config.run.max_episodes,
    )

    latency_summary = "n/a"
    if result.latency_p50_ms is not None and result.latency_p95_ms is not None:
        latency_summary = (
            f"p50={result.latency_p50_ms:.1f}ms p95={result.latency_p95_ms:.1f}ms"
        )

    logger.info(
        "Run complete: env=%s rendered_steps=%d narrations=%d dropped=%d %s",
        env_id,
        result.rendered_steps,
        result.narration_count,
        result.dropped_narration_candidates,
        latency_summary,
    )
    typer.echo(
        "Run complete: "
        f"rendered={result.rendered_steps} "
        f"narrations={result.narration_count} "
        f"dropped={result.dropped_narration_candidates} "
        f"{latency_summary}"
    )


@tune_app.command("prompt")
def tune_prompt(
    ctx: typer.Context,
    env: str | None = typer.Option(None, "--env", help="Gymnasium environment id."),
    samples: int = typer.Option(
        20,
        "--samples",
        min=1,
        help="Number of narrated samples to generate.",
    ),
    step_stride: int = typer.Option(
        5,
        "--step-stride",
        min=1,
        help="Environment steps between narrated samples.",
    ),
    seed: int | None = typer.Option(None, help="Random seed for reset/action space."),
    agent: Literal["random", "scripted", "sb3"] | None = typer.Option(
        None,
        "--agent",
        help="Action source used during prompt tuning.",
    ),
    policy: str | None = typer.Option(
        None,
        "--policy",
        help=(
            "SB3 policy repo shorthand (e.g. sb3/ppo-PongNoFrameskip-v4). "
            "Sets --agent sb3."
        ),
    ),
    repo_id: str | None = typer.Option(
        None,
        "--repo-id",
        help="Hugging Face model repository id for SB3 policy loading.",
    ),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help="Policy filename inside the SB3 Hugging Face repo.",
    ),
    revision: str | None = typer.Option(
        None,
        "--revision",
        help="Optional Hugging Face commit SHA, tag, or branch for SB3 download.",
    ),
    allow_untrusted_repo: bool = typer.Option(
        False,
        "--allow-untrusted-repo",
        help=(
            "Allow SB3 policy loading when trust enforcement is disabled or the "
            "repo id is outside trusted prefixes."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip the interactive untrusted-repo confirmation prompt.",
    ),
    wait_for_vlm: bool = typer.Option(
        False,
        "--wait-for-vlm",
        help="Poll /models until the local VLM endpoint is ready.",
    ),
    wait_timeout: float = typer.Option(
        60.0,
        "--wait-timeout",
        min=1.0,
        help="Maximum seconds to wait when --wait-for-vlm is enabled.",
    ),
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Collect narrated frame samples for prompt-quality comparison runs.

    The command advances the environment in fixed strides, narrates sampled frames,
    and prints latency plus narration text for side-by-side prompt iteration.

    Args:
        ctx: Typer context carrying shared settings.

    Raises:
        typer.Exit: If ``--wait-for-vlm`` is enabled and readiness times out.
        typer.BadParameter: If ``--env-kwargs`` is not valid JSON object input.
    """

    state = _get_state(ctx)
    config = state.settings

    env_id = env or config.run.env_id
    effective_seed = config.run.seed if seed is None else seed
    effective_agent = config.agent.kind if agent is None else agent
    effective_repo_id = repo_id or config.agent.sb3_repo_id
    effective_filename = filename or config.agent.sb3_filename
    effective_revision = revision
    if effective_revision is None and repo_id is None and policy is None:
        effective_revision = config.agent.sb3_revision
    if policy:
        effective_agent = "sb3"
        effective_repo_id = policy
        if filename is None:
            effective_filename = f"{policy.rsplit('/', maxsplit=1)[-1]}.zip"
    effective_enforce_trusted_repo = _resolve_trusted_repo_enforcement(
        agent_kind=effective_agent,
        repo_id=effective_repo_id,
        revision=effective_revision,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
        allow_untrusted_repo=allow_untrusted_repo,
        yes=yes,
    )

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    narrator_class = _load_cli_dependency("VLMNarrator", "docugym.narrator")
    narrator = narrator_class(
        base_url=config.vlm.base_url,
        model=config.vlm.model,
        max_tokens=config.vlm.max_tokens,
        temperature=config.vlm.temperature,
        top_p=config.vlm.top_p,
        image_detail=config.vlm.image_detail,
        system_prompt=config.narration.system_prompt,
    )

    if wait_for_vlm:
        typer.echo(
            f"Waiting for VLM endpoint at {config.vlm.base_url} "
            f"(timeout {wait_timeout:.1f}s)..."
        )
        ready = narrator.wait_until_ready_sync(timeout_seconds=wait_timeout)
        if not ready:
            typer.secho(
                "VLM endpoint did not become ready before timeout. "
                "Start the sidecar and retry.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    prompt_tuning_runner = _load_cli_dependency(
        "run_prompt_tuning",
        "docugym.tune",
    )
    results = prompt_tuning_runner(
        env_id=env_id,
        seed=effective_seed,
        samples=samples,
        step_stride=step_stride,
        narrator=narrator,
        agent_kind=effective_agent,
        sb3_repo_id=effective_repo_id,
        sb3_filename=effective_filename,
        sb3_algorithm=config.agent.sb3_algorithm,
        sb3_device=config.agent.device,
        sb3_revision=effective_revision,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=effective_enforce_trusted_repo,
        env_kwargs=effective_env_kwargs,
    )

    typer.echo(
        "Prompt tuning complete: "
        f"env={env_id} "
        f"samples={len(results)} "
        f"model={config.vlm.model}"
    )

    for index, sample in enumerate(results, start=1):
        typer.echo(
            f"[{index:02d}] "
            f"step={sample.step} "
            f"reward={sample.reward:+.2f} "
            f"latency={sample.latency_ms:.1f}ms"
        )
        typer.echo(sample.narration)

    if results:
        mean_latency_ms = sum(sample.latency_ms for sample in results) / len(results)
        typer.echo(f"Mean narration latency: {mean_latency_ms:.1f}ms")
