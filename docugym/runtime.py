from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from time import perf_counter
from typing import Any, Callable, Literal, Protocol

import numpy as np

from docugym.display import Display
from docugym.env import RandomAgent, ScriptedAgent, load_sb3_policy, make_env
from docugym.narrator import NarrationContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Stage4RunResult:
    """Aggregated metrics from a synchronous Stage 4 narration run."""

    rendered_steps: int
    narration_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class NarratorClient(Protocol):
    """Structural narrator type used by the Stage 4 synchronous runtime loop."""

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a given frame and context."""


def run_stage4_session(
    *,
    env_id: str,
    seed: int,
    fps: int,
    window_scale: int,
    subtitle_font: str,
    subtitle_size: int,
    subtitle_max_text_width: int,
    hud: bool,
    text_bands: bool,
    min_window_width: int,
    env_kwargs: dict[str, Any] | None,
    narrator: NarratorClient,
    narrate_every: int,
    agent_kind: Literal["random", "scripted", "sb3"],
    sb3_repo_id: str | None,
    sb3_filename: str | None,
    max_steps: int | None = None,
    on_narration: Callable[[str, int, float], None] | None = None,
) -> Stage4RunResult:
    """Run gameplay + display, narrating synchronously every N frames."""

    if narrate_every <= 0:
        raise ValueError("narrate_every must be a positive integer")
    if max_steps is not None and max_steps <= 0:
        raise ValueError("max_steps must be a positive integer when provided")

    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    display = Display(
        env_id=env_id,
        fps=fps,
        window_scale=window_scale,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        subtitle_max_text_width=subtitle_max_text_width,
        hud=hud,
        text_bands=text_bands,
        min_window_width=min_window_width,
    )

    random_agent = RandomAgent(env)
    scripted_agent = ScriptedAgent(env_id=env_id, fallback=random_agent)
    policy = None
    policy_disabled = False

    if agent_kind == "sb3":
        if sb3_repo_id is None or sb3_filename is None:
            raise ValueError("sb3_repo_id and sb3_filename are required for SB3 agent")
        policy = load_sb3_policy(repo_id=sb3_repo_id, filename=sb3_filename)

    step = 0
    episode_reward = 0.0
    last_narration = ""
    latency_samples_ms: list[float] = []
    narration_count = 0

    try:
        observation, _ = env.reset(seed=seed)
        display.set_subtitle("A pause. The creature gathers itself.")

        while display.is_open:
            if policy is not None and not policy_disabled:
                try:
                    action, _ = policy.predict(observation, deterministic=True)
                except Exception as exc:  # pragma: no cover - depends on model/runtime
                    logger.warning(
                        "SB3 policy prediction failed, "
                        "falling back to random actions: %s",
                        exc,
                    )
                    policy_disabled = True
                    action = random_agent.act(observation)
            elif agent_kind == "scripted":
                action = scripted_agent.act(observation)
            else:
                action = random_agent.act(observation)

            observation, reward, terminated, truncated, _ = env.step(action)
            episode_reward += float(reward)
            frame = env.render()

            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            step += 1

            if step % narrate_every == 0:
                context = NarrationContext(
                    env_human_name=_env_human_name(env_id),
                    previous_narration=last_narration,
                    event_summary=(
                        f"episode step {step}; reward {float(reward):+.2f}; "
                        f"episode reward {episode_reward:+.2f}"
                    ),
                )

                started = perf_counter()
                try:
                    narration = narrator.narrate_frame_sync(
                        frame=frame, context=context
                    )
                except Exception as exc:
                    logger.warning("Narration request failed at step=%d: %s", step, exc)
                    narration = "A pause. The creature gathers itself."
                latency_ms = (perf_counter() - started) * 1000.0

                narration_count += 1
                latency_samples_ms.append(latency_ms)
                last_narration = narration
                display.set_subtitle(narration)
                logger.info(
                    "Narration[%d] step=%d latency_ms=%.1f text=%s",
                    narration_count,
                    step,
                    latency_ms,
                    narration,
                )
                if on_narration is not None:
                    on_narration(narration, step, latency_ms)

            display.set_status(step=step, episode_reward=episode_reward)
            if not display.blit_frame(frame):
                break

            if max_steps is not None and step >= max_steps:
                break

            if terminated or truncated:
                observation, _ = env.reset()
                episode_reward = 0.0
    finally:
        display.close()
        env.close()

    return Stage4RunResult(
        rendered_steps=step,
        narration_count=narration_count,
        latency_p50_ms=_percentile(latency_samples_ms, 0.50),
        latency_p95_ms=_percentile(latency_samples_ms, 0.95),
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * quantile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]

    lower_weight = upper - rank
    upper_weight = rank - lower
    return ordered[lower] * lower_weight + ordered[upper] * upper_weight


def _env_human_name(env_id: str) -> str:
    return env_id.replace("/", " ").replace("-", " ")
