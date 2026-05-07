from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import numpy as np

from docugym.runtime import SpeechSentence, run_stage4_session, run_stage6_session_sync


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


class FakeInteractiveDisplay(FakeDisplay):
    def __init__(
        self,
        *,
        action_schedule: dict[int, list[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._action_schedule = action_schedule or {}
        self._poll_count = 0
        self.paused_states: list[bool] = []
        self.muted_states: list[bool] = []
        self.narrating_states: list[bool] = []

    def poll_actions(self) -> list[str]:
        self._poll_count += 1
        return list(self._action_schedule.get(self._poll_count, []))

    def set_paused(self, paused: bool) -> None:
        self.paused_states.append(paused)

    def set_muted(self, muted: bool) -> None:
        self.muted_states.append(muted)

    def set_narrating(self, active: bool) -> None:
        self.narrating_states.append(active)


class FakeNarrator:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, int, int], str]] = []

    def narrate_frame_sync(self, frame: np.ndarray, context: Any) -> str:
        self.calls.append((frame.shape, context.event_summary))
        return "The patient traveller drifts onward."


class FakeSpeakerSentence:
    def __init__(self, graphemes: str, chunks: list[np.ndarray]) -> None:
        self.graphemes = graphemes
        self.chunks = chunks


class FakeSpeaker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def speak_sync(self, text: str) -> list[SpeechSentence]:
        self.calls.append(text)
        return cast(
            "list[SpeechSentence]",
            [
                FakeSpeakerSentence(
                    graphemes="The patient traveller drifts onward.",
                    chunks=[np.ones(16, dtype=np.float32)],
                )
            ],
        )


class FakeAudioOutput:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.chunks: list[np.ndarray] = []

    def start(self) -> None:
        self.started = True

    def enqueue(self, chunk: np.ndarray) -> None:
        self.chunks.append(chunk)

    def stop(self) -> None:
        self.stopped = True


class AsyncFakeNarrator:
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[tuple[int, int, int], str]] = []

    async def narrate_frame(self, frame: np.ndarray, context: Any) -> str:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
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


def test_run_stage4_session_queues_tts_audio_when_voice_enabled(monkeypatch) -> None:
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
    speaker = FakeSpeaker()
    audio_output = FakeAudioOutput()

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
        voice_enabled=True,
        speaker=speaker,
        audio_output=audio_output,
        max_steps=4,
    )

    display = displays[0]

    assert result.rendered_steps == 4
    assert result.narration_count == 2
    assert audio_output.started is True
    assert audio_output.stopped is True
    assert len(audio_output.chunks) == 2
    assert speaker.calls == [
        "The patient traveller drifts onward.",
        "The patient traveller drifts onward.",
    ]
    assert "The patient traveller drifts onward." in display.subtitles


def test_run_stage6_session_narrates_on_reward_spikes(monkeypatch) -> None:
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

    narrator = AsyncFakeNarrator()
    result = run_stage6_session_sync(
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
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=0.5,
        pixel_delta_threshold=999.0,
        max_context_events=3,
        previous_narration_window=2,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        voice_enabled=False,
        max_steps=6,
    )

    display = displays[0]
    assert result.rendered_steps == 6
    assert result.narration_count >= 1
    assert result.dropped_narration_candidates == 0
    assert len(narrator.calls) >= 1
    assert env.closed is True
    assert display.closed is True


def test_run_stage6_session_drops_stale_candidates_under_backpressure(
    monkeypatch,
) -> None:
    env = DummyEnv()

    def fake_make_env(**_kwargs: Any) -> DummyEnv:
        return env

    def fake_display(**kwargs: Any) -> FakeDisplay:
        return FakeDisplay(**kwargs)

    monkeypatch.setattr("docugym.runtime.make_env", fake_make_env)
    monkeypatch.setattr("docugym.runtime.Display", fake_display)

    slow_narrator = AsyncFakeNarrator(delay_seconds=0.01)
    result = run_stage6_session_sync(
        env_id="ALE/Pong-v5",
        seed=5,
        fps=240,
        window_scale=3,
        subtitle_font="DejaVu Sans",
        subtitle_size=22,
        subtitle_max_text_width=960,
        hud=True,
        text_bands=True,
        min_window_width=960,
        env_kwargs={},
        narrator=slow_narrator,
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=0.5,
        pixel_delta_threshold=999.0,
        max_context_events=3,
        previous_narration_window=2,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        voice_enabled=False,
        max_steps=25,
    )

    assert result.rendered_steps == 25
    assert result.narration_count >= 1
    assert result.dropped_narration_candidates >= 1


def test_run_stage6_session_force_narrate_shortcut(monkeypatch) -> None:
    env = DummyEnv()
    displays: list[FakeInteractiveDisplay] = []

    def fake_make_env(**_kwargs: Any) -> DummyEnv:
        return env

    def fake_display(**kwargs: Any) -> FakeInteractiveDisplay:
        instance = FakeInteractiveDisplay(
            action_schedule={1: ["force_narrate"]},
            **kwargs,
        )
        displays.append(instance)
        return instance

    monkeypatch.setattr("docugym.runtime.make_env", fake_make_env)
    monkeypatch.setattr("docugym.runtime.Display", fake_display)

    narrator = AsyncFakeNarrator()
    result = run_stage6_session_sync(
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
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=999.0,
        pixel_delta_threshold=999.0,
        max_context_events=3,
        previous_narration_window=2,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        voice_enabled=False,
        max_steps=4,
    )

    display = displays[0]
    assert result.narration_count >= 1
    assert len(narrator.calls) >= 1
    assert display.closed is True


def test_run_stage6_session_shortcuts_mute_and_save_clip(monkeypatch) -> None:
    env = DummyEnv()
    displays: list[FakeInteractiveDisplay] = []
    saved_calls: list[tuple[int, str]] = []

    def fake_make_env(**_kwargs: Any) -> DummyEnv:
        return env

    def fake_display(**kwargs: Any) -> FakeInteractiveDisplay:
        instance = FakeInteractiveDisplay(
            action_schedule={1: ["toggle_mute", "save_clip", "force_narrate"]},
            **kwargs,
        )
        displays.append(instance)
        return instance

    def fake_save_clip_snapshot(
        *,
        frame: np.ndarray,
        step: int,
        narration: str,
        out_dir: Path = Path("out/clips"),
    ) -> tuple[Path, Path]:
        del frame, out_dir
        saved_calls.append((step, narration))
        return Path("out/clips/snapshot.png"), Path("out/clips/snapshot.txt")

    monkeypatch.setattr("docugym.runtime.make_env", fake_make_env)
    monkeypatch.setattr("docugym.runtime.Display", fake_display)
    monkeypatch.setattr("docugym.runtime._save_clip_snapshot", fake_save_clip_snapshot)

    narrator = AsyncFakeNarrator()
    speaker = FakeSpeaker()
    audio_output = FakeAudioOutput()

    result = run_stage6_session_sync(
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
        narration_interval_seconds=999.0,
        min_gap_seconds=0.0,
        reward_spike_threshold=999.0,
        pixel_delta_threshold=999.0,
        max_context_events=3,
        previous_narration_window=2,
        agent_kind="random",
        sb3_repo_id=None,
        sb3_filename=None,
        voice_enabled=True,
        speaker=speaker,
        audio_output=audio_output,
        max_steps=4,
    )

    display = displays[0]
    assert result.narration_count >= 1
    assert audio_output.started is True
    assert audio_output.stopped is True
    assert audio_output.chunks == []
    assert saved_calls
    assert saved_calls[0][1]
    assert True in display.muted_states
