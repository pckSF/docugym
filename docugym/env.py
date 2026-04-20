from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Literal, Protocol

import gymnasium as gym
import numpy as np

POLICY_CACHE_DIR = Path.home() / ".cache" / "docugym" / "policies"


class Policy(Protocol):
    """Minimal policy protocol for Stable-Baselines3-compatible inference."""

    def predict(
        self,
        observation: Any,
        state: Any | None = None,
        episode_start: Any | None = None,
        deterministic: bool = True,
    ) -> tuple[Any, Any | None]:
        """Return an action and optional recurrent state for an observation."""


class RandomAgent:
    """Agent that samples actions directly from the environment action space."""

    def __init__(self, env: Any) -> None:
        self._env = env

    def act(self, observation: Any) -> Any:
        """Sample an action from the environment action space."""

        del observation
        return self._env.action_space.sample()


class ScriptedAgent:
    """Simple heuristic agent for quick smoke checks in known environments."""

    def __init__(self, env_id: str, fallback: RandomAgent | None = None) -> None:
        self._env_id = env_id
        self._fallback = fallback

    def act(self, observation: Any) -> int:
        """Return a deterministic action for supported envs or fallback action."""

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
    """Create and seed an RGB-array Gymnasium environment."""

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
    env.reset(seed=seed)
    return env


def _resolve_cached_policy_path(repo_id: str, filename: str) -> Path:
    repo_dir = repo_id.replace("/", "--")
    return POLICY_CACHE_DIR / repo_dir / filename


def _download_policy(repo_id: str, filename: str, destination: Path) -> Path:
    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_sb3 import load_from_hub
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "SB3 policy download requires huggingface-sb3. "
            "Install huggingface-sb3 to use --agent sb3."
        ) from exc

    downloaded_path = Path(load_from_hub(repo_id=repo_id, filename=filename))
    if downloaded_path.resolve() != destination.resolve():
        shutil.copy2(downloaded_path, destination)

    return destination


def _load_policy_from_path(filename: str, model_path: Path) -> Policy:
    algo_name = filename.split("-", maxsplit=1)[0].lower()

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

    return loader.load(str(model_path), device="cpu")


def load_sb3_policy(repo_id: str, filename: str) -> Policy:
    """Download (if needed) and load an SB3 policy from Hugging Face Hub."""

    cache_path = _resolve_cached_policy_path(repo_id=repo_id, filename=filename)
    model_path = _download_policy(
        repo_id=repo_id,
        filename=filename,
        destination=cache_path,
    )
    return _load_policy_from_path(filename=filename, model_path=model_path)


def _save_frame_png(frame: np.ndarray, path: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError("Pillow is required to write smoketest PNG frames.") from exc

    frame_to_save = frame
    if frame_to_save.dtype != np.uint8:
        frame_to_save = np.clip(frame_to_save, 0, 255).astype(np.uint8)

    Image.fromarray(frame_to_save).save(path, format="PNG")


def run_smoketest(
    env_id: str,
    seed: int,
    steps: int,
    out_dir: Path,
    env_kwargs: dict[str, Any] | None = None,
    agent_kind: Literal["random", "scripted", "sb3"] = "random",
    sb3_repo_id: str | None = None,
    sb3_filename: str | None = None,
) -> list[Path]:
    """Step an environment and persist rendered frames for smoke validation."""

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
        policy = load_sb3_policy(repo_id=sb3_repo_id, filename=sb3_filename)

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
            _save_frame_png(frame=frame, path=frame_path)
            frame_paths.append(frame_path)

            if terminated or truncated:
                observation, _ = env.reset()
    finally:
        env.close()

    return frame_paths
