from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal, Protocol

import numpy as np

from docugym.env import Policy, RandomAgent, ScriptedAgent, load_sb3_policy, make_env
from docugym.narrator import NarrationContext


class SyncNarrator(Protocol):
    """Minimal sync narrator interface used by prompt tuning helpers."""

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a single frame and context payload."""


@dataclass(slots=True)
class PromptTuningSample:
    """One narrated sample emitted by the Stage 10 prompt tuning command."""

    step: int
    reward: float
    narration: str
    latency_ms: float


def _humanize_env_id(env_id: str) -> str:
    return env_id.replace("/", " ").replace("-", " ")


def _choose_action(
    *,
    observation: Any,
    random_agent: RandomAgent,
    scripted_agent: ScriptedAgent | None,
    policy: Policy | None,
) -> Any:
    if policy is not None:
        action, _ = policy.predict(observation, deterministic=True)
        return action

    if scripted_agent is not None:
        return scripted_agent.act(observation)

    return random_agent.act(observation)


def run_prompt_tuning(
    *,
    env_id: str,
    seed: int,
    samples: int,
    step_stride: int,
    narrator: SyncNarrator,
    agent_kind: Literal["random", "scripted", "sb3"],
    sb3_repo_id: str | None,
    sb3_filename: str | None,
    trusted_repo_prefixes: list[str] | tuple[str, ...] | None,
    enforce_trusted_repo: bool,
    env_kwargs: dict[str, Any] | None = None,
) -> list[PromptTuningSample]:
    """Collect frame samples and generate narration text for prompt A/B tuning."""

    if samples <= 0:
        raise ValueError("samples must be a positive integer")
    if step_stride <= 0:
        raise ValueError("step_stride must be a positive integer")
    if agent_kind == "sb3" and (sb3_repo_id is None or sb3_filename is None):
        raise ValueError("sb3_repo_id and sb3_filename are required for SB3 agent")

    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    random_agent = RandomAgent(env)

    scripted_agent: ScriptedAgent | None = None
    policy: Policy | None = None
    if agent_kind == "scripted":
        scripted_agent = ScriptedAgent(env_id=env_id, fallback=random_agent)
    elif agent_kind == "sb3":
        policy = load_sb3_policy(
            repo_id=sb3_repo_id,
            filename=sb3_filename,
            trusted_repo_prefixes=trusted_repo_prefixes,
            enforce_trusted_repo=enforce_trusted_repo,
        )

    rendered_step = 0
    previous_narration = ""
    collected: list[PromptTuningSample] = []

    try:
        observation, _ = env.reset(seed=seed)

        while len(collected) < samples:
            reward = 0.0

            for _ in range(step_stride):
                action = _choose_action(
                    observation=observation,
                    random_agent=random_agent,
                    scripted_agent=scripted_agent,
                    policy=policy,
                )
                observation, reward, terminated, truncated, _ = env.step(action)
                rendered_step += 1

                if terminated or truncated:
                    observation, _ = env.reset()

            frame = env.render()
            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            context = NarrationContext(
                env_human_name=_humanize_env_id(env_id),
                previous_narration=previous_narration,
                event_summary=f"episode step {rendered_step}; reward {float(reward):+.2f}",
            )

            started = perf_counter()
            narration = narrator.narrate_frame_sync(frame=frame, context=context)
            latency_ms = (perf_counter() - started) * 1000.0

            previous_narration = narration
            collected.append(
                PromptTuningSample(
                    step=rendered_step,
                    reward=float(reward),
                    narration=narration,
                    latency_ms=latency_ms,
                )
            )
    finally:
        env.close()

    return collected
