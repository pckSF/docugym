from __future__ import annotations

from collections import defaultdict
import time
from typing import Any

import gymnasium as gym
import numpy as np

from docugym.wrapper import docuwrapper


class DummyEnv(gym.Env[np.ndarray, int]):
    def __init__(self) -> None:
        self.action_space = gym.spaces.Discrete(2)
        self.observation_space = gym.spaces.Box(
            low=-100.0,
            high=100.0,
            shape=(1,),
            dtype=np.float32,
        )
        self.step_count = 0
        self.closed = False

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        del seed, options
        self.step_count = 0
        return np.array([0.0], dtype=np.float32), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        del action
        self.step_count += 1
        return (
            np.array([float(self.step_count)], dtype=np.float32),
            1.0,
            False,
            False,
            {},
        )

    def render(self) -> np.ndarray:
        return np.full((8, 8, 3), fill_value=self.step_count, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeDisplay:
    instances: list["FakeDisplay"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_open = True
        self._subtitle = ""
        self._status: tuple[int, float] = (0, 0.0)
        self._paused = False
        self._muted = False
        self._narrating = False
        self._poll_count = 0
        self.blit_calls = 0
        self.action_schedule: dict[int, list[str]] = defaultdict(list)
        self.closed = False
        FakeDisplay.instances.append(self)

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text

    def set_status(self, step: int, episode_reward: float) -> None:
        self._status = (step, episode_reward)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_muted(self, muted: bool) -> None:
        self._muted = muted

    def set_narrating(self, active: bool) -> None:
        self._narrating = active

    def blit_frame(self, frame: np.ndarray) -> bool:
        del frame
        self.blit_calls += 1
        return self.is_open

    def poll_actions(self) -> list[str]:
        self._poll_count += 1
        return list(self.action_schedule.get(self._poll_count, []))

    def close(self) -> None:
        self.closed = True
        self.is_open = False


class FakeNarrator:
    def __init__(self, **kwargs: Any) -> None:
        del kwargs

    def narrate_frame_sync(self, frame: np.ndarray, context: Any) -> str:
        del frame, context
        return "The patient traveller drifts onward."


def _wait_until(predicate: Any, timeout_seconds: float = 1.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_docuwrapper_emits_info_and_callbacks(monkeypatch) -> None:
    FakeDisplay.instances.clear()
    monkeypatch.setattr("docugym.wrapper.Display", FakeDisplay)
    monkeypatch.setattr("docugym.wrapper.VLMNarrator", FakeNarrator)

    narrations: list[tuple[str, int, float]] = []
    subtitles: list[str] = []

    wrapper = docuwrapper(
        DummyEnv(),
        env_id="CartPole-v1",
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=0.5,
        pixel_delta_threshold=999.0,
        voice_enabled=False,
        on_narration=(
            lambda text, step, latency: narrations.append((text, step, latency))
        ),
        on_subtitle=subtitles.append,
    )

    try:
        _, reset_info = wrapper.reset(seed=5)
        assert "docugym" in reset_info

        _, _, _, _, step_info = wrapper.step(0)
        ready = _wait_until(lambda: wrapper.state()["narration_count"] >= 1)
        assert ready is True

        assert "docugym" in step_info
        assert step_info["docugym"]["narration_count"] >= 0
        assert narrations
        assert subtitles
        assert step_info["docugym"]["latest_narration"]
    finally:
        wrapper.close()


def test_docuwrapper_pause_action_holds_frame(monkeypatch) -> None:
    FakeDisplay.instances.clear()
    monkeypatch.setattr("docugym.wrapper.Display", FakeDisplay)
    monkeypatch.setattr("docugym.wrapper.VLMNarrator", FakeNarrator)

    wrapper = docuwrapper(
        DummyEnv(),
        env_id="CartPole-v1",
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=999.0,
        pixel_delta_threshold=999.0,
        voice_enabled=False,
    )

    try:
        _, _ = wrapper.reset(seed=3)
        display = FakeDisplay.instances[0]
        display.action_schedule[1] = ["toggle_pause"]
        display.action_schedule[2] = ["toggle_pause"]

        _, _, _, _, _ = wrapper.step(0)

        assert display.blit_calls >= 2
        assert wrapper.state()["paused"] is False
    finally:
        wrapper.close()


def test_docuwrapper_force_narrate_action(monkeypatch) -> None:
    FakeDisplay.instances.clear()
    monkeypatch.setattr("docugym.wrapper.Display", FakeDisplay)
    monkeypatch.setattr("docugym.wrapper.VLMNarrator", FakeNarrator)

    wrapper = docuwrapper(
        DummyEnv(),
        env_id="CartPole-v1",
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=999.0,
        pixel_delta_threshold=999.0,
        voice_enabled=False,
    )

    try:
        _, _ = wrapper.reset(seed=3)
        display = FakeDisplay.instances[0]
        display.action_schedule[1] = ["force_narrate"]

        _, _, _, _, _ = wrapper.step(0)
        ready = _wait_until(lambda: wrapper.state()["narration_count"] >= 1)

        assert ready is True
        assert wrapper.state()["latest_narration"]
    finally:
        wrapper.close()
