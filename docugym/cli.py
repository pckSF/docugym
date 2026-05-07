from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Literal

import typer
import yaml

from docugym.config import AppSettings, load_settings
from docugym.display import run_display_smoketest
from docugym.env import run_smoketest
from docugym.logging_config import configure_logging
from docugym.narrator import VLMNarrator
from docugym.runtime import run_session_sync
from docugym.tune import run_prompt_tuning

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

_PRESET_NAMES: tuple[str, ...] = ("atari", "lunarlander", "carracing")


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


def _load_preset_settings(config_path: Path) -> AppSettings:
    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw_data is None:
        raw_data = {}
    if not isinstance(raw_data, dict):
        raise ValueError("Preset config must decode to a YAML mapping")
    return AppSettings.model_validate(raw_data)


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


@app.command("list-voices")
def list_voices() -> None:
    """Print Kokoro's supported British voices with short sample lines."""

    typer.echo("Kokoro British voices:")
    for voice_id, sample in _KOKORO_BRITISH_VOICE_SAMPLES:
        typer.echo(f"- {voice_id}: {sample}")


@app.command("list-envs")
def list_envs() -> None:
    """Print environment presets shipped in configs/."""

    config_dir = Path("configs")
    typer.echo("Supported env presets:")

    found = False
    for preset_name in _PRESET_NAMES:
        preset_path = config_dir / f"{preset_name}.yaml"
        if not preset_path.exists():
            continue
        settings = _load_preset_settings(preset_path)
        policy = settings.agent.sb3_repo_id if settings.agent.kind == "sb3" else "n/a"
        typer.echo(
            "- "
            f"{preset_name}: env={settings.run.env_id} "
            f"agent={settings.agent.kind} policy={policy}"
        )
        found = True

    if not found:
        typer.echo("- no presets found in configs/")


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
    env_kwargs: str | None = typer.Option(
        None,
        "--env-kwargs",
        help="JSON object of extra kwargs passed to gym.make().",
    ),
) -> None:
    """Run a local smoke test and persist rendered frames to disk."""

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
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
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
    """Run the live display loop with a random agent."""

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
    """Run the async narration pipeline with keyframe selection."""

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
    if policy:
        effective_agent = "sb3"
        effective_repo_id = policy
        if filename is None:
            effective_filename = f"{policy.rsplit('/', maxsplit=1)[-1]}.zip"

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    narrator = VLMNarrator(
        base_url=config.vlm.base_url,
        model=config.vlm.model,
        max_tokens=config.vlm.max_tokens,
        temperature=config.vlm.temperature,
        top_p=config.vlm.top_p,
        image_detail=config.vlm.image_detail,
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

    result = run_session_sync(
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
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
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
    """Generate multiple narrations over varied frames for prompt tuning."""

    state = _get_state(ctx)
    config = state.settings

    env_id = env or config.run.env_id
    effective_seed = config.run.seed if seed is None else seed
    effective_agent = config.agent.kind if agent is None else agent
    effective_repo_id = repo_id or config.agent.sb3_repo_id
    effective_filename = filename or config.agent.sb3_filename
    if policy:
        effective_agent = "sb3"
        effective_repo_id = policy
        if filename is None:
            effective_filename = f"{policy.rsplit('/', maxsplit=1)[-1]}.zip"

    effective_env_kwargs: dict[str, Any] = {}
    if env is None or env_id == config.run.env_id:
        effective_env_kwargs.update(config.run.env_kwargs)
    effective_env_kwargs.update(_parse_env_kwargs(env_kwargs))

    narrator = VLMNarrator(
        base_url=config.vlm.base_url,
        model=config.vlm.model,
        max_tokens=config.vlm.max_tokens,
        temperature=config.vlm.temperature,
        top_p=config.vlm.top_p,
        image_detail=config.vlm.image_detail,
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

    results = run_prompt_tuning(
        env_id=env_id,
        seed=effective_seed,
        samples=samples,
        step_stride=step_stride,
        narrator=narrator,
        agent_kind=effective_agent,
        sb3_repo_id=effective_repo_id,
        sb3_filename=effective_filename,
        trusted_repo_prefixes=config.agent.trusted_repo_prefixes,
        enforce_trusted_repo=config.agent.enforce_trusted_repo,
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

    mean_latency_ms = sum(sample.latency_ms for sample in results) / len(results)
    typer.echo(f"Mean narration latency: {mean_latency_ms:.1f}ms")
