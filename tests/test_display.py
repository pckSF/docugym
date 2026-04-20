from __future__ import annotations

from typing import Any

import numpy as np

from docugym.display import Display, run_display_smoketest


class DummyActionSpace:
    def sample(self) -> int:
        return 1


class DummyEnv:
    def __init__(self) -> None:
        self.action_space = DummyActionSpace()
        self.reset_calls: list[int | None] = []
        self.step_count = 0
        self.closed = False

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, str]]:
        self.reset_calls.append(seed)
        return np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, str]]:
        del action
        self.step_count += 1
        terminated = self.step_count == 3
        observation = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        return observation, 1.0, terminated, False, {}

    def render(self) -> np.ndarray:
        return np.full((6, 8, 3), fill_value=self.step_count, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeDisplay:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.status_updates: list[tuple[int, float]] = []
        self.frames = 0
        self.subtitle = ""
        self.is_open = True
        self.closed = False

    def set_subtitle(self, text: str) -> None:
        self.subtitle = text

    def set_status(self, step: int, episode_reward: float) -> None:
        self.status_updates.append((step, episode_reward))

    def blit_frame(self, frame: np.ndarray) -> bool:
        del frame
        self.frames += 1
        return True

    def close(self) -> None:
        self.closed = True
        self.is_open = False


def test_normalize_frame_clips_to_uint8_and_drops_alpha() -> None:
    frame = np.array(
        [
            [[-2.0, 40.0, 300.0, 12.0], [1.0, 2.0, 3.0, 4.0]],
            [[5.0, 6.0, 7.0, 8.0], [9.0, 10.0, 11.0, 12.0]],
        ],
        dtype=np.float32,
    )

    normalized = Display._normalize_frame(frame)

    assert normalized.dtype == np.uint8
    assert normalized.shape == (2, 2, 3)
    assert normalized[0, 0].tolist() == [0, 40, 255]


def test_run_display_smoketest_updates_status_and_resets_reward(monkeypatch) -> None:
    env = DummyEnv()
    display_instances: list[FakeDisplay] = []

    def fake_make_env(**_kwargs: Any) -> DummyEnv:
        return env

    def fake_display_factory(**kwargs: Any) -> FakeDisplay:
        instance = FakeDisplay(**kwargs)
        display_instances.append(instance)
        return instance

    monkeypatch.setattr("docugym.display.make_env", fake_make_env)
    monkeypatch.setattr("docugym.display.Display", fake_display_factory)

    rendered = run_display_smoketest(
        env_id="ALE/Breakout-v5",
        seed=7,
        fps=60,
        window_scale=3,
        subtitle="Stub subtitle",
        subtitle_font="DejaVu Sans",
        subtitle_size=22,
        hud=True,
        max_steps=5,
    )

    display = display_instances[0]

    assert rendered == 5
    assert display.subtitle == "Stub subtitle"
    assert display.status_updates[0] == (1, 1.0)
    assert display.status_updates[3] == (4, 1.0)
    assert display.closed is True
    assert env.closed is True
    assert env.reset_calls == [7, None]
