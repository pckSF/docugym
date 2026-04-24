from __future__ import annotations

from typing import Any

import numpy as np

from docugym.runtime import run_stage4_session


class DummyActionSpace:
    def sample(self) -> int:
        return 1

    def seed(self, seed: int) -> None:
        del seed


class DummyEnv:
    def __init__(self) -> None:
        self.action_space = DummyActionSpace()
        self.step_count = 0
        self.reset_calls: list[int | None] = []
        self.closed = False

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, object]]:
        self.reset_calls.append(seed)
        return np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32), {}

    def step(
        self,
        action: int,
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, object]]:
        del action
        self.step_count += 1
        terminated = self.step_count == 3
        return (
            np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            1.0,
            terminated,
            False,
            {},
        )

    def render(self) -> np.ndarray:
        return np.full((6, 8, 3), fill_value=self.step_count, dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeDisplay:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_open = True
        self.closed = False
        self.status_updates: list[tuple[int, float]] = []
        self.subtitles: list[str] = []

    def set_subtitle(self, text: str) -> None:
        self.subtitles.append(text)

    def set_status(self, step: int, episode_reward: float) -> None:
        self.status_updates.append((step, episode_reward))

    def blit_frame(self, frame: np.ndarray) -> bool:
        del frame
        return True

    def close(self) -> None:
        self.closed = True
        self.is_open = False


class FakeNarrator:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, int, int], str]] = []

    def narrate_frame_sync(self, frame: np.ndarray, context: Any) -> str:
        self.calls.append((frame.shape, context.event_summary))
        return "The patient traveller drifts onward."


def test_run_stage4_session_narrates_on_fixed_cadence(monkeypatch) -> None:
    env = DummyEnv()
    displays: list[FakeDisplay] = []

    def fake_make_env(**_kwargs: Any) -> DummyEnv:
        return env

    def fake_display(**kwargs: Any) -> FakeDisplay:
        instance = FakeDisplay(**kwargs)
        displays.append(instance)
        return instance

    monkeypatch.setattr("docugym.runtime.make_env", fake_make_env)
    monkeypatch.setattr("docugym.runtime.Display", fake_display)

    narrator = FakeNarrator()

    result = run_stage4_session(
        env_id="ALE/Pong-v5",
        seed=5,
        fps=60,
        window_scale=3,
        subtitle_font="DejaVu Sans",
        subtitle_size=22,
        subtitle_max_text_width=960,
        hud=True,
        text_bands=True,
        min_window_width=960,
        env_kwargs={},
        narrator=narrator,
        narrate_every=2,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        max_steps=5,
    )

    display = displays[0]

    assert result.rendered_steps == 5
    assert result.narration_count == 2
    assert result.latency_p50_ms is not None
    assert result.latency_p95_ms is not None
    assert len(narrator.calls) == 2
    assert env.closed is True
    assert display.closed is True
    assert display.status_updates[0] == (1, 1.0)
    assert display.subtitles[0] == "A pause. The creature gathers itself."
