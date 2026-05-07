from __future__ import annotations

import numpy as np
import pytest

from docugym.narrator import NarrationContext
from docugym.tune import PromptTuningSample, run_prompt_tuning


class DummyActionSpace:
    def sample(self) -> int:
        return 1

    def seed(self, seed: int) -> None:
        del seed


class DummyEnv:
    def __init__(self) -> None:
        self.action_space = DummyActionSpace()
        self.step_count = 0
        self.closed = False

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, object]]:
        del seed
        return np.array([0.0], dtype=np.float32), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, object]]:
        del action
        self.step_count += 1
        terminated = self.step_count % 5 == 0
        observation = np.array([float(self.step_count)], dtype=np.float32)
        reward = float(self.step_count)
        return observation, reward, terminated, False, {}

    def render(self) -> np.ndarray:
        return np.full((4, 4, 3), fill_value=self.step_count, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeNarrator:
    def __init__(self) -> None:
        self.calls: list[NarrationContext] = []

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        assert isinstance(frame, np.ndarray)
        self.calls.append(context)
        return f"Narration {len(self.calls)}"


def test_run_prompt_tuning_collects_samples_and_keeps_context(monkeypatch) -> None:
    env = DummyEnv()
    narrator = FakeNarrator()

    monkeypatch.setattr("docugym.tune.make_env", lambda **_kwargs: env)

    samples = run_prompt_tuning(
        env_id="CartPole-v1",
        seed=7,
        samples=3,
        step_stride=2,
        narrator=narrator,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        trusted_repo_prefixes=["sb3/"],
        enforce_trusted_repo=False,
        env_kwargs={"frameskip": 2},
    )

    assert len(samples) == 3
    assert all(isinstance(sample, PromptTuningSample) for sample in samples)
    assert [sample.step for sample in samples] == [2, 4, 6]
    assert narrator.calls[0].env_human_name == "CartPole v1"
    assert narrator.calls[1].previous_narration == "Narration 1"
    assert env.closed is True


def test_run_prompt_tuning_requires_sb3_identifiers(monkeypatch) -> None:
    called = False

    def fake_make_env(**_kwargs: object) -> DummyEnv:
        nonlocal called
        called = True
        return DummyEnv()

    monkeypatch.setattr("docugym.tune.make_env", fake_make_env)

    with pytest.raises(ValueError, match="sb3_repo_id and sb3_filename"):
        _ = run_prompt_tuning(
            env_id="CartPole-v1",
            seed=7,
            samples=2,
            step_stride=1,
            narrator=FakeNarrator(),
            agent_kind="sb3",
            sb3_repo_id=None,
            sb3_filename=None,
            trusted_repo_prefixes=["sb3/"],
            enforce_trusted_repo=False,
            env_kwargs=None,
        )

    assert called is False
