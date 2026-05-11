"""Environment factories, lightweight agents, and SB3 policy loading helpers.

Both CLI smoke tests and live runtime paths use this module to keep environment
construction and trusted-policy loading behavior consistent.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any, Literal, Protocol, Sequence

import gymnasium as gym
import numpy as np

from docugym.image_io import save_frame_png

POLICY_CACHE_DIR = Path.home() / ".cache" / "docugym" / "policies"
DEFAULT_TRUSTED_SB3_REPO_PREFIXES: tuple[str, ...] = ("sb3/",)

logger = logging.getLogger(__name__)


class Policy(Protocol):
    """Minimal policy protocol for Stable-Baselines3-compatible inference.

    Implementations return ``(action, recurrent_state)`` tuples compatible with
    DocuGym runtime/wrapper stepping loops.
    """

    def predict(
        self,
        observation: Any,
        state: Any | None = None,
        episode_start: Any | None = None,
        deterministic: bool = True,
    ) -> tuple[Any, Any | None]:
        """Return an action and optional recurrent state for an observation.

        Args:
            observation: Current environment observation.
            state: Optional recurrent-policy state.
            episode_start: Optional episode-start flag payload.
            deterministic: Whether policy should act deterministically.

        Returns:
            Tuple of ``(action, next_state)``.
        """


class RandomAgent:
    """Agent that samples actions from the environment action space.

    This agent is intentionally stateless and is used as the baseline fallback in
    smoke tests and runtime degradation paths.
    """

    def __init__(self, env: Any) -> None:
        self._env = env

    def act(self, observation: Any) -> Any:
        """Sample one action from the environment action space.

        Args:
            observation: Unused observation payload kept for interface parity.

        Returns:
            Environment action sampled from ``action_space``.
        """

        del observation
        return self._env.action_space.sample()


class ScriptedAgent:
    """Tiny deterministic policy used for reproducible smoke-test behavior.

    The heuristics are intentionally narrow and fallback to random actions for
    unsupported environments.

    Currently includes deterministic policies for ``MountainCar-v0`` and
    ``CartPole-v1`` smoke-test behavior.
    """

    def __init__(self, env_id: str, fallback: RandomAgent | None = None) -> None:
        self._env_id = env_id
        self._fallback = fallback

    def act(self, observation: Any) -> int:
        """Return a deterministic action for known envs or fallback action.

        Args:
            observation: Current observation used by environment-specific heuristics.

        Returns:
            Integer action id.
        """

        if self._env_id == "MountainCar-v0":
            # Always accelerate right to provide deterministic smoke-test behavior.
            return 2

        if self._env_id == "CartPole-v1":
            angle = float(np.asarray(observation)[2])
            return 1 if angle >= 0.0 else 0

        if self._fallback is None:
            return 0

        return int(self._fallback.act(observation))


def make_env(
    env_id: str,
    seed: int,
    env_kwargs: dict[str, Any] | None = None,
) -> gym.Env[Any, Any]:
    """Create a seeded ``rgb_array`` Gymnasium environment instance.

    Atari ids trigger lazy ALE registration so users do not need a separate
    registration step in CLI or runtime call paths.

    Args:
        env_id: Gymnasium environment id.
        seed: Reset/action-space seed.
        env_kwargs: Optional kwargs forwarded to ``gym.make``.

    Returns:
        Seeded environment configured for ``render_mode='rgb_array'``.

    Raises:
        RuntimeError: If ALE support is required but not installed.
    """

    if env_id.startswith("ALE/"):
        try:
            import ale_py
        except ImportError as exc:  # pragma: no cover - exercised in integration
            raise RuntimeError(
                "ALE environments require ale-py. Install with gymnasium Atari extras."
            ) from exc
        gym.register_envs(ale_py)

    kwargs = dict(env_kwargs or {})
    env = gym.make(env_id, render_mode="rgb_array", **kwargs)
    env.action_space.seed(seed)
    return env


def _resolve_cached_policy_path(
    repo_id: str,
    filename: str,
    revision: str | None = None,
) -> Path:
    """Build a deterministic cache path for one downloaded SB3 policy file."""

    repo_dir = repo_id.replace("/", "--")
    if revision:
        revision_dir = revision.replace("/", "--")
        return POLICY_CACHE_DIR / repo_dir / revision_dir / filename
    return POLICY_CACHE_DIR / repo_dir / filename


def _download_policy(
    repo_id: str,
    filename: str,
    destination: Path,
    revision: str | None = None,
) -> Path:
    """Download one policy artifact and store it at the canonical cache path.

    ``huggingface_hub`` may return a path in its own cache tree; this function
    mirrors the file into DocuGym's cache layout so later lookups are stable.
    """

    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "SB3 policy download requires huggingface-hub. "
            "Install huggingface-hub to use --agent sb3."
        ) from exc

    downloaded_path = Path(
        hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)
    )
    if downloaded_path.resolve() != destination.resolve():
        shutil.copy2(downloaded_path, destination)

    return destination


def _load_policy_from_path(
    filename: str,
    model_path: Path,
    *,
    algorithm: str | None = None,
    device: str = "cpu",
) -> Policy:
    """Load an SB3 policy checkpoint from disk.

    If ``algorithm`` is omitted, the loader infers it from the filename prefix to
    preserve compatibility with standard SB3 artifact naming.

    Raises:
        ValueError: If no supported SB3 loader matches the algorithm prefix.
        RuntimeError: If Stable-Baselines3 is not installed.
    """

    algo_name = (algorithm or filename.split("-", maxsplit=1)[0]).lower()

    try:
        from stable_baselines3 import A2C, DQN, PPO, SAC, TD3
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "Stable-Baselines3 is required for SB3 policy loading. "
            "Install stable-baselines3 to use --agent sb3."
        ) from exc

    loaders: dict[str, type[Any]] = {
        "a2c": A2C,
        "dqn": DQN,
        "ppo": PPO,
        "sac": SAC,
        "td3": TD3,
    }

    loader = loaders.get(algo_name)
    if loader is None:
        supported = ", ".join(sorted(loaders))
        raise ValueError(
            f"Unsupported SB3 algorithm prefix '{algo_name}'. "
            f"Supported prefixes: {supported}."
        )

    return loader.load(str(model_path), device=device)


def _normalize_repo_prefixes(
    trusted_repo_prefixes: Sequence[str] | None,
) -> tuple[str, ...]:
    """Return cleaned trust prefixes, falling back to project defaults."""

    if trusted_repo_prefixes is None:
        return DEFAULT_TRUSTED_SB3_REPO_PREFIXES

    normalized = tuple(prefix.strip() for prefix in trusted_repo_prefixes if prefix)
    if not normalized:
        return DEFAULT_TRUSTED_SB3_REPO_PREFIXES
    return normalized


def _is_trusted_repo(repo_id: str, trusted_prefixes: tuple[str, ...]) -> bool:
    """Check whether a repo id starts with one of the configured trust prefixes."""

    return any(repo_id.startswith(prefix) for prefix in trusted_prefixes)


def load_sb3_policy(
    repo_id: str,
    filename: str,
    *,
    trusted_repo_prefixes: Sequence[str] | None = None,
    enforce_trusted_repo: bool = True,
    revision: str | None = None,
    algorithm: str | None = None,
    device: str = "cpu",
) -> Policy:
    """Download and load an SB3 policy, with optional trust enforcement.

    Stable-Baselines3 policy loading deserializes model artifacts. Loading an
    untrusted policy can execute arbitrary code during deserialization.

    Args:
        repo_id: Hugging Face repository id.
        filename: Policy artifact filename within the repository.
        trusted_repo_prefixes: Optional allowlist of trusted repo id prefixes.
        enforce_trusted_repo: Whether untrusted repos raise instead of warn.
        revision: Optional repository revision pin.
        algorithm: Optional explicit SB3 algorithm name.
        device: Device string forwarded to SB3 loader.

    Returns:
        Loaded SB3-compatible policy object.

    Raises:
        ValueError: If trust checks fail or algorithm is unsupported.
        RuntimeError: If download or SB3 dependencies are unavailable.
    """

    trusted_prefixes = _normalize_repo_prefixes(trusted_repo_prefixes)
    if not _is_trusted_repo(repo_id, trusted_prefixes):
        message = (
            "Untrusted SB3 repo id '%s' does not match trusted prefixes %s. "
            "SB3 policy deserialization can execute arbitrary code."
        )
        if enforce_trusted_repo:
            raise ValueError(message % (repo_id, trusted_prefixes))
        logger.warning(message, repo_id, trusted_prefixes)

    cache_path = _resolve_cached_policy_path(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
    )
    model_path = _download_policy(
        repo_id=repo_id,
        filename=filename,
        destination=cache_path,
        revision=revision,
    )
    return _load_policy_from_path(
        filename=filename,
        model_path=model_path,
        algorithm=algorithm,
        device=device,
    )


def run_smoketest(
    env_id: str,
    seed: int,
    steps: int,
    out_dir: Path,
    env_kwargs: dict[str, Any] | None = None,
    agent_kind: Literal["random", "scripted", "sb3"] = "random",
    sb3_repo_id: str | None = None,
    sb3_filename: str | None = None,
    trusted_repo_prefixes: Sequence[str] | None = None,
    enforce_trusted_repo: bool = True,
    sb3_revision: str | None = None,
    sb3_algorithm: str | None = None,
    sb3_device: str = "cpu",
) -> list[Path]:
    """Run a fixed-length smoke test and save rendered frame PNGs.

    This is primarily a validation helper for confirming environment creation,
    policy loading, and render-mode behavior in CI and local setup checks.

    Args:
        env_id: Gymnasium environment id.
        seed: Reset/action-space seed.
        steps: Number of frames to capture.
        out_dir: Output directory for PNG frame artifacts.
        env_kwargs: Optional kwargs forwarded to ``gym.make``.
        agent_kind: Action source (``random``, ``scripted``, or ``sb3``).
        sb3_repo_id: SB3 repository id when ``agent_kind='sb3'``.
        sb3_filename: SB3 artifact filename when ``agent_kind='sb3'``.
        trusted_repo_prefixes: Optional trusted repo prefix allowlist.
        enforce_trusted_repo: Whether untrusted repos raise instead of warn.
        sb3_revision: Optional SB3 repository revision pin.
        sb3_algorithm: Optional explicit SB3 algorithm override.
        sb3_device: SB3 loader device string.

    Returns:
        Ordered list of saved frame paths.

    Raises:
        ValueError: If ``steps`` is non-positive or required SB3 options are
            missing.
        TypeError: If environment render output is not ``numpy.ndarray``.
    """

    if steps <= 0:
        raise ValueError("steps must be a positive integer")

    out_dir.mkdir(parents=True, exist_ok=True)
    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    random_agent = RandomAgent(env)

    scripted_agent: ScriptedAgent | None = None
    policy: Policy | None = None
    if agent_kind == "scripted":
        scripted_agent = ScriptedAgent(env_id=env_id, fallback=random_agent)
    elif agent_kind == "sb3":
        if sb3_repo_id is None or sb3_filename is None:
            raise ValueError("sb3_repo_id and sb3_filename are required for SB3 agent")
        policy = load_sb3_policy(
            repo_id=sb3_repo_id,
            filename=sb3_filename,
            trusted_repo_prefixes=trusted_repo_prefixes,
            enforce_trusted_repo=enforce_trusted_repo,
            revision=sb3_revision,
            algorithm=sb3_algorithm,
            device=sb3_device,
        )

    frame_paths: list[Path] = []

    try:
        observation, _ = env.reset(seed=seed)

        for step_idx in range(steps):
            if policy is not None:
                action, _ = policy.predict(observation, deterministic=True)
            elif scripted_agent is not None:
                action = scripted_agent.act(observation)
            else:
                action = random_agent.act(observation)

            observation, _, terminated, truncated, _ = env.step(action)
            frame = env.render()

            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            frame_path = out_dir / f"frame-{step_idx:05d}.png"
            save_frame_png(frame=frame, path=frame_path)
            frame_paths.append(frame_path)

            if terminated or truncated:
                observation, _ = env.reset()
    finally:
        env.close()

    return frame_paths
