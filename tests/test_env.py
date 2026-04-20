from __future__ import annotations

from pathlib import Path
import sys
import types
from typing import cast

import numpy as np

from docugym.env import (
    POLICY_CACHE_DIR,
    RandomAgent,
    ScriptedAgent,
    load_sb3_policy,
    make_env,
    run_smoketest,
)


class DummyActionSpace:
    def __init__(self, sample_value: int = 1) -> None:
        self.sample_value = sample_value
        self.seed_value: int | None = None

    def sample(self) -> int:
        return self.sample_value

    def seed(self, seed: int) -> None:
        self.seed_value = seed


class DummyEnv:
    def __init__(self) -> None:
        self.action_space = DummyActionSpace(sample_value=3)
        self.reset_calls: list[int | None] = []
        self.step_count = 0
        self.closed = False

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, str]]:
        self.reset_calls.append(seed)
        return np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32), {}

    def step(
        self,
        action: int,
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, str]]:
        self.step_count += 1
        terminated = self.step_count % 3 == 0
        observation = np.array([action, 0.0, 0.0, 0.0], dtype=np.float32)
        return observation, 0.0, terminated, False, {}

    def render(self) -> np.ndarray:
        return np.full((8, 8, 3), fill_value=self.step_count, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class DummyAlgo:
    load_calls: list[str] = []

    @classmethod
    def load(cls, path: str, **_kwargs: object) -> dict[str, str]:
        cls.load_calls.append(path)
        return {"loaded_from": path}


def test_make_env_registers_ale_envs_and_seeds(monkeypatch) -> None:
    env = DummyEnv()
    make_calls: dict[str, object] = {}

    def fake_make(env_id: str, **kwargs: object) -> DummyEnv:
        make_calls["env_id"] = env_id
        make_calls["kwargs"] = kwargs
        return env

    register_calls: list[types.ModuleType] = []

    def fake_register_envs(module: types.ModuleType) -> None:
        register_calls.append(module)

    ale_module = types.ModuleType("ale_py")
    monkeypatch.setitem(sys.modules, "ale_py", ale_module)
    monkeypatch.setattr("docugym.env.gym.make", fake_make)
    monkeypatch.setattr("docugym.env.gym.register_envs", fake_register_envs)

    created_env = make_env(
        env_id="ALE/Breakout-v5",
        seed=123,
        env_kwargs={"frameskip": 4, "repeat_action_probability": 0.25},
    )

    assert created_env is env
    assert make_calls["env_id"] == "ALE/Breakout-v5"
    assert make_calls["kwargs"] == {
        "render_mode": "rgb_array",
        "frameskip": 4,
        "repeat_action_probability": 0.25,
    }
    assert register_calls == [ale_module]
    assert env.action_space.seed_value == 123
    assert env.reset_calls == [123]


def test_make_env_non_ale_does_not_register(monkeypatch) -> None:
    env = DummyEnv()
    monkeypatch.setattr("docugym.env.gym.make", lambda _env_id, **_kwargs: env)
    monkeypatch.setattr(
        "docugym.env.gym.register_envs",
        lambda _module: (_ for _ in ()).throw(AssertionError("unexpected register")),
    )

    created_env = make_env(env_id="CartPole-v1", seed=7)

    assert created_env is env
    assert env.action_space.seed_value == 7


def test_random_agent_samples_from_action_space() -> None:
    env = DummyEnv()
    env.action_space = DummyActionSpace(sample_value=9)

    agent = RandomAgent(env)

    assert agent.act(observation=np.array([1.0])) == 9


def test_scripted_agent_heuristics_and_fallback() -> None:
    random_env = DummyEnv()
    random_env.action_space = DummyActionSpace(sample_value=5)
    fallback = RandomAgent(random_env)

    mountain_agent = ScriptedAgent(env_id="MountainCar-v0", fallback=fallback)
    cartpole_agent = ScriptedAgent(env_id="CartPole-v1", fallback=fallback)
    unknown_agent = ScriptedAgent(env_id="LunarLander-v3", fallback=fallback)

    assert mountain_agent.act(np.array([0.0, 0.0])) == 2
    assert cartpole_agent.act(np.array([0.0, 0.0, 0.2, 0.0])) == 1
    assert cartpole_agent.act(np.array([0.0, 0.0, -0.2, 0.0])) == 0
    assert unknown_agent.act(np.array([0.0])) == 5


def test_load_sb3_policy_downloads_to_docugym_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_id = "sb3/ppo-LunarLander-v2"
    filename = "ppo-LunarLander-v2.zip"

    downloaded = tmp_path / "downloaded.zip"
    downloaded.write_text("model", encoding="utf-8")

    hf_calls: list[tuple[str, str]] = []
    hf_module = types.ModuleType("huggingface_sb3")

    def fake_load_from_hub(*, repo_id: str, filename: str) -> str:
        hf_calls.append((repo_id, filename))
        return str(downloaded)

    setattr(hf_module, "load_from_hub", fake_load_from_hub)

    sb3_module = types.ModuleType("stable_baselines3")
    setattr(sb3_module, "A2C", DummyAlgo)
    setattr(sb3_module, "DQN", DummyAlgo)
    setattr(sb3_module, "PPO", DummyAlgo)
    setattr(sb3_module, "SAC", DummyAlgo)
    setattr(sb3_module, "TD3", DummyAlgo)

    monkeypatch.setitem(sys.modules, "huggingface_sb3", hf_module)
    monkeypatch.setitem(sys.modules, "stable_baselines3", sb3_module)
    monkeypatch.setattr("docugym.env.POLICY_CACHE_DIR", tmp_path / "cache")
    DummyAlgo.load_calls = []

    first = cast("dict[str, str]", load_sb3_policy(repo_id=repo_id, filename=filename))
    second = cast("dict[str, str]", load_sb3_policy(repo_id=repo_id, filename=filename))

    cache_path = (tmp_path / "cache" / "sb3--ppo-LunarLander-v2" / filename).resolve()

    assert Path(first["loaded_from"]).resolve() == cache_path
    assert Path(second["loaded_from"]).resolve() == cache_path
    assert hf_calls == [(repo_id, filename)]
    assert cache_path.exists()
    assert DummyAlgo.load_calls == [str(cache_path), str(cache_path)]


def test_run_smoketest_saves_requested_number_of_frames(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env = DummyEnv()
    monkeypatch.setattr("docugym.env.make_env", lambda **_kwargs: env)

    frame_paths = run_smoketest(
        env_id="CartPole-v1",
        seed=11,
        steps=5,
        out_dir=tmp_path / "frames",
        agent_kind="scripted",
    )

    assert len(frame_paths) == 5
    assert all(path.exists() for path in frame_paths)
    assert env.closed is True


def test_policy_cache_dir_constant_uses_home() -> None:
    assert isinstance(POLICY_CACHE_DIR, Path)
