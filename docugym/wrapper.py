from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import queue
import threading
from time import perf_counter
from typing import Any, Callable

import gymnasium as gym
import numpy as np

from docugym.audio import AudioOutput
from docugym.clips import save_clip_snapshot
from docugym.display import Display
from docugym.display_actions import build_action_transitions, poll_display_actions
from docugym.keyframes import KeyframeSelector
from docugym.narration_events import (
    format_event_summary,
    humanize_env_id,
    join_previous_narrations,
    join_recent_events,
)
from docugym.narrator import NarrationContext, VLMNarrator
from docugym.queue_utils import drain_latest_sync, push_drop_oldest_sync
from docugym.tts import KokoroTTS, SpeechSentence

logger = logging.getLogger(__name__)


NarrationCallback = Callable[[str, int, float], None]
SubtitleCallback = Callable[[str], None]
AudioChunkCallback = Callable[[np.ndarray], None]
StatusCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class _NarrationRequest:
    """Frame and context payload queued for narration synthesis."""

    frame: np.ndarray
    step: int
    context_summary: str
    previous_narration: str
    timestamp: float


@dataclass(slots=True)
class _WrapperStats:
    """Mutable counters for wrapper runtime observability."""

    narration_count: int = 0
    dropped_narration_candidates: int = 0
    last_latency_ms: float | None = None


_save_clip_snapshot = save_clip_snapshot


def _resolve_env_id(env: gym.Env[Any, Any], env_id: str | None) -> str:
    if env_id:
        return env_id

    spec = getattr(env, "spec", None)
    spec_id = getattr(spec, "id", None)
    if isinstance(spec_id, str) and spec_id:
        return spec_id

    return env.__class__.__name__


class DocuWrapper(gym.Wrapper):
    """Gym wrapper that overlays live narration, subtitles, and optional voice."""

    def __init__(
        self,
        env: gym.Env[Any, Any],
        *,
        env_id: str | None = None,
        fps: int = 60,
        window_scale: int = 3,
        subtitle_font: str = "DejaVu Sans",
        subtitle_size: int = 22,
        subtitle_max_text_width: int = 960,
        hud: bool = True,
        text_bands: bool = True,
        min_window_width: int = 960,
        narrator: VLMNarrator | None = None,
        base_url: str = "http://localhost:8000/v1",
        model: str = "Qwen/Qwen3-VL-8B-Instruct-AWQ",
        max_tokens: int = 80,
        temperature: float = 0.8,
        top_p: float = 0.9,
        image_detail: str = "low",
        narration_interval_seconds: float = 3.0,
        min_gap_seconds: float = 1.5,
        reward_spike_threshold: float = 5.0,
        pixel_delta_threshold: float = 8.0,
        max_context_events: int = 3,
        previous_narration_window: int = 2,
        voice_enabled: bool = False,
        tts_engine: str = "kokoro",
        tts_voice: str = "bm_george",
        tts_speed: float = 0.95,
        tts_sample_rate: int = 24_000,
        speaker: KokoroTTS | None = None,
        audio_output: AudioOutput | None = None,
        on_narration: NarrationCallback | None = None,
        on_subtitle: SubtitleCallback | None = None,
        on_audio_chunk: AudioChunkCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> None:
        super().__init__(env)

        if narration_interval_seconds <= 0:
            raise ValueError("narration_interval_seconds must be positive")
        if min_gap_seconds < 0:
            raise ValueError("min_gap_seconds must be non-negative")
        if max_context_events <= 0:
            raise ValueError("max_context_events must be positive")
        if previous_narration_window <= 0:
            raise ValueError("previous_narration_window must be positive")

        self._env_id = _resolve_env_id(env, env_id)
        self._narrator = narrator or VLMNarrator(
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            image_detail=image_detail,
        )

        self._display = Display(
            env_id=self._env_id,
            fps=fps,
            window_scale=window_scale,
            subtitle_font=subtitle_font,
            subtitle_size=subtitle_size,
            subtitle_max_text_width=subtitle_max_text_width,
            hud=hud,
            text_bands=text_bands,
            min_window_width=min_window_width,
        )
        self._display.set_subtitle("A pause. The creature gathers itself.")

        self._voice_enabled = voice_enabled
        self._audio_output: AudioOutput | None = None
        self._speaker: KokoroTTS | None = None
        if self._voice_enabled:
            if tts_engine != "kokoro":
                raise ValueError("Only the 'kokoro' TTS engine is currently supported")
            self._audio_output = audio_output or AudioOutput(
                sample_rate=tts_sample_rate,
            )
            self._speaker = speaker or KokoroTTS(
                voice=tts_voice,
                speed=tts_speed,
                sample_rate=tts_sample_rate,
            )
            self._audio_output.start()

        self._keyframe_selector = KeyframeSelector(
            interval_seconds=narration_interval_seconds,
            min_gap_seconds=min_gap_seconds,
            reward_spike_threshold=reward_spike_threshold,
            pixel_delta_threshold=pixel_delta_threshold,
        )

        self._on_narration = on_narration
        self._on_subtitle = on_subtitle
        self._on_audio_chunk = on_audio_chunk
        self._on_status = on_status

        self._stats = _WrapperStats()
        self._stats_lock = threading.Lock()

        self._recent_events: deque[str] = deque(maxlen=max_context_events)
        self._previous_narrations: deque[str] = deque(maxlen=previous_narration_window)

        self._subtitle_queue: queue.Queue[str] = queue.Queue(maxsize=8)
        self._narration_queue: queue.Queue[_NarrationRequest] = queue.Queue(maxsize=2)

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self._session_step = 0
        self._episode_reward = 0.0
        self._latest_frame: np.ndarray | None = None
        self._latest_narration = "A pause. The creature gathers itself."
        self._latest_subtitle = self._latest_narration

        self._paused = False
        self._narrating = False
        self._audio_muted = not self._voice_enabled
        self._window_open = True
        self._closed = False

        self._display.set_paused(self._paused)
        self._display.set_narrating(self._narrating)
        self._display.set_muted(self._audio_muted)

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Reset wrapped environment and draw the first narrated frame."""

        self._ensure_open()
        self._start_worker_if_needed()

        observation, info = self.env.reset(seed=seed, options=options)
        self._episode_reward = 0.0
        self._paused = False
        self._display.set_paused(self._paused)

        frame = self.env.render()
        frame_array = self._require_frame(frame)
        self._latest_frame = frame_array
        self._keyframe_selector.reset(
            previous_frame=np.array(frame_array, copy=True),
            timestamp=perf_counter(),
        )

        self._render_current_frame(frame_array)
        if not self._window_open:
            logger.info("DocuWrapper window closed during reset")

        return observation, self._augment_info(info)

    def step(self, action: Any) -> tuple[Any, float, bool, bool, dict[str, Any]]:
        """Step wrapped environment while updating narration and subtitle state."""

        self._ensure_open()
        self._hold_if_paused()

        observation, reward, terminated, truncated, info = self.env.step(action)
        reward_value = float(reward)
        self._session_step += 1
        self._episode_reward += reward_value

        frame = self.env.render()
        frame_array = self._require_frame(frame)
        self._latest_frame = frame_array

        self._maybe_enqueue_narration(
            frame=frame_array,
            reward=reward_value,
            terminated=terminated,
            truncated=truncated,
        )

        self._render_current_frame(frame_array)
        self._handle_actions(frame_array)
        self._hold_if_paused()

        if self._window_open is False:
            truncated = True

        if terminated or truncated:
            self._episode_reward = 0.0

        return (
            observation,
            reward_value,
            terminated,
            truncated,
            self._augment_info(info),
        )

    def close(self) -> None:
        """Stop wrapper background workers and close wrapped resources."""

        if self._closed:
            return

        self._closed = True
        self._stop_event.set()

        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

        if self._audio_output is not None:
            self._audio_output.stop()

        self._display.close()
        self.env.close()

    def state(self) -> dict[str, Any]:
        """Return current wrapper runtime state and narration counters."""

        with self._stats_lock:
            payload = {
                "step": self._session_step,
                "episode_reward": self._episode_reward,
                "narration_count": self._stats.narration_count,
                "dropped_narration_candidates": (
                    self._stats.dropped_narration_candidates
                ),
                "last_latency_ms": self._stats.last_latency_ms,
                "latest_narration": self._latest_narration,
                "latest_subtitle": self._latest_subtitle,
                "paused": self._paused,
                "muted": self._audio_muted,
                "narrating": self._narrating,
                "window_open": self._window_open,
                "voice_enabled": self._voice_enabled,
            }

        return payload

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("DocuWrapper is closed")

    def _start_worker_if_needed(self) -> None:
        if self._worker_thread is not None:
            return

        self._worker_thread = threading.Thread(
            target=self._worker_main,
            name="docuwrapper-narration-worker",
            daemon=True,
        )
        self._worker_thread.start()

    def _worker_main(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._narration_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            context = NarrationContext(
                env_human_name=humanize_env_id(self._env_id),
                previous_narration=request.previous_narration,
                event_summary=request.context_summary,
            )

            started = perf_counter()
            try:
                narration = self._narrator.narrate_frame_sync(
                    frame=request.frame,
                    context=context,
                )
            except Exception as exc:
                logger.warning(
                    "Narration request failed at step=%d: %s",
                    request.step,
                    exc,
                )
                narration = "A pause. The creature gathers itself."

            latency_ms = (perf_counter() - started) * 1000.0
            self._record_narration_result(narration=narration, latency_ms=latency_ms)

            if self._on_narration is not None:
                self._safe_callback(
                    callback=lambda: self._on_narration(
                        narration,
                        request.step,
                        latency_ms,
                    ),
                    name="on_narration",
                )

            if (
                not self._voice_enabled
                or self._speaker is None
                or self._audio_output is None
            ):
                continue

            if self._audio_muted:
                continue

            self._set_narrating(True)
            try:
                sentences = self._speaker.speak_sync(narration)
                for sentence in sentences:
                    if self._audio_muted:
                        break
                    self._emit_sentence(sentence)
            except Exception as exc:
                logger.warning("TTS synthesis failed in wrapper mode: %s", exc)
            finally:
                self._set_narrating(False)

    def _record_narration_result(self, *, narration: str, latency_ms: float) -> None:
        with self._stats_lock:
            self._stats.narration_count += 1
            self._stats.last_latency_ms = latency_ms
            self._previous_narrations.append(narration)
            self._latest_narration = narration

        self._push_subtitle(narration)

    def _emit_sentence(self, sentence: SpeechSentence) -> None:
        subtitle_text = sentence.graphemes.strip()
        if subtitle_text:
            self._push_subtitle(subtitle_text)

        for chunk in sentence.chunks:
            if self._audio_muted:
                break
            self._audio_output.enqueue(chunk)
            if self._on_audio_chunk is not None:
                self._safe_callback(
                    callback=lambda: self._on_audio_chunk(chunk),
                    name="on_audio_chunk",
                )

    def _safe_callback(self, *, callback: Callable[[], None], name: str) -> None:
        try:
            callback()
        except Exception as exc:  # pragma: no cover - user callback failure path
            logger.warning("Ignoring %s callback failure: %s", name, exc)

    def _push_subtitle(self, text: str) -> None:
        dropped = push_drop_oldest_sync(self._subtitle_queue, text)
        if dropped:
            logger.info("Dropped stale subtitle update due queue pressure")

        with self._stats_lock:
            self._latest_subtitle = text

        if self._on_subtitle is not None:
            self._safe_callback(
                callback=lambda: self._on_subtitle(text),
                name="on_subtitle",
            )

    def _render_current_frame(self, frame: np.ndarray) -> None:
        subtitle = drain_latest_sync(self._subtitle_queue)
        if isinstance(subtitle, str):
            self._display.set_subtitle(subtitle)

        self._display.set_status(
            step=self._session_step,
            episode_reward=self._episode_reward,
        )
        self._display.set_narrating(self._narrating)
        self._display.set_paused(self._paused)
        self._display.set_muted(self._audio_muted)

        self._window_open = self._display.blit_frame(frame)

        if self._on_status is not None:
            state = self.state()
            self._safe_callback(
                callback=lambda: self._on_status(state),
                name="on_status",
            )

    def _handle_actions(self, frame: np.ndarray) -> None:
        actions = poll_display_actions(self._display)
        for transition in build_action_transitions(
            actions,
            paused=self._paused,
            muted=self._audio_muted,
        ):
            action = transition.action
            if action == "toggle_pause":
                self._paused = transition.paused
                self._display.set_paused(self._paused)
                continue

            if action == "toggle_mute":
                self._audio_muted = transition.muted
                self._display.set_muted(self._audio_muted)
                if self._audio_muted and self._audio_output is not None:
                    self._audio_output.clear()
                continue

            if action == "force_narrate":
                self._enqueue_narration(
                    frame=frame,
                    reward=0.0,
                    manual=True,
                    timestamp=perf_counter(),
                )
                continue

            if action == "save_clip":
                self._save_clip(frame)

    def _save_clip(self, frame: np.ndarray) -> None:
        frame_copy = np.array(frame, copy=True)
        with self._stats_lock:
            narration = self._latest_narration
        try:
            frame_path, narration_path = _save_clip_snapshot(
                frame=frame_copy,
                step=self._session_step,
                narration=narration,
            )
            logger.info(
                "Saved wrapper clip snapshot: frame=%s narration=%s",
                frame_path,
                narration_path,
            )
        except Exception as exc:  # pragma: no cover - depends on host filesystem
            logger.warning("Failed to save wrapper clip snapshot: %s", exc)

    def _hold_if_paused(self) -> None:
        if not self._paused or self._latest_frame is None:
            return

        while self._paused and self._window_open and not self._stop_event.is_set():
            self._render_current_frame(self._latest_frame)
            self._handle_actions(self._latest_frame)

    def _maybe_enqueue_narration(
        self,
        *,
        frame: np.ndarray,
        reward: float,
        terminated: bool,
        truncated: bool,
    ) -> None:
        now = perf_counter()
        decision = self._keyframe_selector.consider(
            frame=frame,
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            timestamp=now,
        )
        if decision is None:
            return

        self._enqueue_narration(
            frame=frame,
            reward=reward,
            reasons=decision.reasons,
            visual_delta=decision.visual_delta,
            manual=False,
            timestamp=now,
        )

    def _enqueue_narration(
        self,
        *,
        frame: np.ndarray,
        reward: float,
        reasons: list[str] | None = None,
        visual_delta: float | None = None,
        manual: bool,
        timestamp: float,
    ) -> None:
        trigger_reasons = reasons or ["manual"]
        event_summary = format_event_summary(
            step=self._session_step,
            reward=reward,
            episode_reward=self._episode_reward,
            visual_delta=visual_delta,
            triggers=trigger_reasons,
        )

        self._recent_events.append(event_summary)
        context_summary = join_recent_events(self._recent_events)

        with self._stats_lock:
            previous_narration = join_previous_narrations(self._previous_narrations)

        dropped = push_drop_oldest_sync(
            self._narration_queue,
            _NarrationRequest(
                frame=np.array(frame, copy=True),
                step=self._session_step,
                context_summary=context_summary,
                previous_narration=previous_narration,
                timestamp=perf_counter(),
            ),
        )
        if dropped:
            with self._stats_lock:
                self._stats.dropped_narration_candidates += 1
            logger.info(
                "Dropped stale wrapper narration candidate at step=%d",
                self._session_step,
            )
        else:
            self._keyframe_selector.mark_narration_enqueued(timestamp=timestamp)

    @staticmethod
    def _require_frame(frame: Any) -> np.ndarray:
        if not isinstance(frame, np.ndarray):
            raise TypeError(
                "Expected render_mode='rgb_array' to return numpy.ndarray, "
                f"got {type(frame)!r}"
            )
        return frame

    def _augment_info(self, info: dict[str, Any]) -> dict[str, Any]:
        info_out = dict(info)
        info_out["docugym"] = self.state()
        return info_out

    def _set_narrating(self, active: bool) -> None:
        with self._stats_lock:
            self._narrating = active


def docuwrapper(env: gym.Env[Any, Any], **kwargs: Any) -> DocuWrapper:
    """Return a Gym-compatible DocuWrapper around an existing environment."""

    return DocuWrapper(env=env, **kwargs)
