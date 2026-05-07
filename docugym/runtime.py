from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import math
from time import perf_counter
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Literal,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np

from docugym.display import Display
from docugym.env import (
    DEFAULT_TRUSTED_SB3_REPO_PREFIXES,
    RandomAgent,
    ScriptedAgent,
    load_sb3_policy,
    make_env,
)
from docugym.narrator import NarrationContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Stage4RunResult:
    """Aggregated metrics from a narration run."""

    rendered_steps: int
    narration_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    dropped_narration_candidates: int = 0


@dataclass(slots=True)
class _FrameEvent:
    """Frame metadata emitted by the environment producer task."""

    frame: np.ndarray
    step: int
    reward: float
    episode_reward: float
    terminated: bool
    truncated: bool
    timestamp: float


@dataclass(slots=True)
class _DisplayEvent:
    """Display payload containing the latest frame and status counters."""

    frame: np.ndarray
    step: int
    episode_reward: float


@dataclass(slots=True)
class _NarrationCandidate:
    """Selected frame candidate forwarded to the narrator worker."""

    frame: np.ndarray
    step: int
    event_summary: str
    timestamp: float


@runtime_checkable
class AsyncNarratorClient(Protocol):
    """Async narrator contract used by the Stage 6 pipeline."""

    async def narrate_frame(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a selected keyframe."""


@runtime_checkable
class AsyncSpeakerClient(Protocol):
    """Async speaker interface used by the Stage 6 pipeline."""

    def speak(self, text: str) -> AsyncIterator[SpeechSentence]:
        """Yield sentence-level speech outputs for a narration text."""


@runtime_checkable
class NarratorClient(Protocol):
    """Structural narrator type used by the Stage 4 synchronous runtime loop."""

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a given frame and context."""


class SpeechSentence(Protocol):
    """Sentence-level TTS output used for subtitle and audio streaming."""

    graphemes: str
    chunks: list[np.ndarray]


@runtime_checkable
class SpeakerClient(Protocol):
    """Synchronous speaker interface used by the runtime loop."""

    def speak_sync(self, text: str) -> Sequence[SpeechSentence]:
        """Synthesize sentence-level audio chunks for a narration text."""


@runtime_checkable
class AudioOutputClient(Protocol):
    """Audio output sink contract used by the runtime loop."""

    def start(self) -> None:
        """Start the audio callback stream."""

    def enqueue(self, chunk: np.ndarray) -> None:
        """Queue one mono float32 chunk for playback."""

    def stop(self) -> None:
        """Stop and release audio stream resources."""


def run_stage4_session(
    *,
    env_id: str,
    seed: int,
    fps: int,
    window_scale: int,
    subtitle_font: str,
    subtitle_size: int,
    subtitle_max_text_width: int,
    hud: bool,
    text_bands: bool,
    min_window_width: int,
    env_kwargs: dict[str, Any] | None,
    narrator: NarratorClient,
    narrate_every: int,
    agent_kind: Literal["random", "scripted", "sb3"],
    sb3_repo_id: str | None,
    sb3_filename: str | None,
    trusted_repo_prefixes: list[str] | tuple[str, ...] = (
        DEFAULT_TRUSTED_SB3_REPO_PREFIXES
    ),
    enforce_trusted_repo: bool = False,
    voice_enabled: bool = False,
    tts_engine: Literal["kokoro", "xtts", "chatterbox"] = "kokoro",
    tts_voice: str = "bm_george",
    tts_speed: float = 0.95,
    tts_sample_rate: int = 24_000,
    speaker: SpeakerClient | None = None,
    audio_output: AudioOutputClient | None = None,
    max_steps: int | None = None,
    on_narration: Callable[[str, int, float], None] | None = None,
) -> Stage4RunResult:
    """Run gameplay + display, narrating synchronously every N frames."""

    if narrate_every <= 0:
        raise ValueError("narrate_every must be a positive integer")
    if max_steps is not None and max_steps <= 0:
        raise ValueError("max_steps must be a positive integer when provided")

    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    display = Display(
        env_id=env_id,
        fps=fps,
        window_scale=window_scale,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        subtitle_max_text_width=subtitle_max_text_width,
        hud=hud,
        text_bands=text_bands,
        min_window_width=min_window_width,
    )

    random_agent = RandomAgent(env)
    scripted_agent = ScriptedAgent(env_id=env_id, fallback=random_agent)
    policy = None
    policy_disabled = False
    active_speaker = speaker
    active_audio_output = audio_output
    tts_active = voice_enabled

    if agent_kind == "sb3":
        if sb3_repo_id is None or sb3_filename is None:
            raise ValueError("sb3_repo_id and sb3_filename are required for SB3 agent")
        policy = load_sb3_policy(
            repo_id=sb3_repo_id,
            filename=sb3_filename,
            trusted_repo_prefixes=trusted_repo_prefixes,
            enforce_trusted_repo=enforce_trusted_repo,
        )

    if voice_enabled:
        try:
            if tts_engine != "kokoro":
                raise ValueError(
                    "Only 'kokoro' tts_engine is currently supported in Stage 5"
                )

            if active_audio_output is None:
                from docugym.audio import AudioOutput

                active_audio_output = AudioOutput(sample_rate=tts_sample_rate)

            if active_speaker is None:
                from docugym.tts import KokoroTTS

                active_speaker = KokoroTTS(
                    voice=tts_voice,
                    speed=tts_speed,
                    sample_rate=tts_sample_rate,
                )

            active_audio_output.start()
        except Exception as exc:
            logger.warning(
                "Voice mode unavailable; continuing subtitle-only narration: %s",
                exc,
            )
            tts_active = False

    step = 0
    episode_reward = 0.0
    last_narration = ""
    latency_samples_ms: list[float] = []
    narration_count = 0

    try:
        observation, _ = env.reset(seed=seed)
        display.set_subtitle("A pause. The creature gathers itself.")

        while display.is_open:
            if policy is not None and not policy_disabled:
                try:
                    action, _ = policy.predict(observation, deterministic=True)
                except Exception as exc:  # pragma: no cover - depends on model/runtime
                    logger.warning(
                        "SB3 policy prediction failed, "
                        "falling back to random actions: %s",
                        exc,
                    )
                    policy_disabled = True
                    action = random_agent.act(observation)
            elif agent_kind == "scripted":
                action = scripted_agent.act(observation)
            else:
                action = random_agent.act(observation)

            observation, reward, terminated, truncated, _ = env.step(action)
            episode_reward += float(reward)
            frame = env.render()

            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            step += 1

            if step % narrate_every == 0:
                context = NarrationContext(
                    env_human_name=_env_human_name(env_id),
                    previous_narration=last_narration,
                    event_summary=(
                        f"episode step {step}; reward {float(reward):+.2f}; "
                        f"episode reward {episode_reward:+.2f}"
                    ),
                )

                started = perf_counter()
                try:
                    narration = narrator.narrate_frame_sync(
                        frame=frame, context=context
                    )
                except Exception as exc:
                    logger.warning("Narration request failed at step=%d: %s", step, exc)
                    narration = "A pause. The creature gathers itself."
                latency_ms = (perf_counter() - started) * 1000.0

                narration_count += 1
                latency_samples_ms.append(latency_ms)
                last_narration = narration
                display.set_subtitle(narration)

                if (
                    tts_active
                    and active_speaker is not None
                    and active_audio_output is not None
                ):
                    try:
                        for sentence in active_speaker.speak_sync(narration):
                            subtitle_text = sentence.graphemes.strip()
                            if subtitle_text:
                                display.set_subtitle(subtitle_text)
                            for chunk in sentence.chunks:
                                active_audio_output.enqueue(chunk)
                    except Exception as exc:
                        logger.warning(
                            "TTS synthesis failed at step=%d; "
                            "continuing subtitle-only: %s",
                            step,
                            exc,
                        )

                logger.info(
                    "Narration[%d] step=%d latency_ms=%.1f text=%s",
                    narration_count,
                    step,
                    latency_ms,
                    narration,
                )
                if on_narration is not None:
                    on_narration(narration, step, latency_ms)

            display.set_status(step=step, episode_reward=episode_reward)
            if not display.blit_frame(frame):
                break

            if max_steps is not None and step >= max_steps:
                break

            if terminated or truncated:
                observation, _ = env.reset()
                episode_reward = 0.0
    finally:
        if tts_active and active_audio_output is not None:
            active_audio_output.stop()
        display.close()
        env.close()

    return Stage4RunResult(
        rendered_steps=step,
        narration_count=narration_count,
        latency_p50_ms=_percentile(latency_samples_ms, 0.50),
        latency_p95_ms=_percentile(latency_samples_ms, 0.95),
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * quantile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]

    lower_weight = upper - rank
    upper_weight = rank - lower
    return ordered[lower] * lower_weight + ordered[upper] * upper_weight


def _env_human_name(env_id: str) -> str:
    return env_id.replace("/", " ").replace("-", " ")


def _mean_abs_pixel_delta(current: np.ndarray, previous: np.ndarray) -> float:
    current_rgb = current[:, :, :3].astype(np.float32, copy=False)
    previous_rgb = previous[:, :, :3].astype(np.float32, copy=False)
    return float(np.mean(np.abs(current_rgb - previous_rgb)))


def _push_drop_oldest(queue_obj: asyncio.Queue[Any], item: Any) -> bool:
    """Enqueue without blocking, dropping the oldest queued item when full."""

    dropped = False
    if queue_obj.full():
        try:
            _ = queue_obj.get_nowait()
            dropped = True
        except asyncio.QueueEmpty:
            dropped = False

    try:
        queue_obj.put_nowait(item)
    except asyncio.QueueFull:
        dropped = True

    return dropped


def _drain_latest(
    queue_obj: asyncio.Queue[Any],
    initial: Any | None = None,
) -> Any | None:
    latest = initial
    while True:
        try:
            latest = queue_obj.get_nowait()
        except asyncio.QueueEmpty:
            break
    return latest


async def _narrate_async(
    narrator: AsyncNarratorClient | NarratorClient,
    frame: np.ndarray,
    context: NarrationContext,
) -> str:
    if isinstance(narrator, AsyncNarratorClient):
        return await narrator.narrate_frame(frame=frame, context=context)

    if isinstance(narrator, NarratorClient):
        return await asyncio.to_thread(
            narrator.narrate_frame_sync,
            frame,
            context,
        )

    raise TypeError("Narrator must implement narrate_frame or narrate_frame_sync")


async def _speak_async(
    speaker: AsyncSpeakerClient | SpeakerClient,
    text: str,
) -> AsyncIterator[SpeechSentence]:
    if isinstance(speaker, AsyncSpeakerClient):
        async for sentence in speaker.speak(text):
            yield sentence
        return

    if isinstance(speaker, SpeakerClient):
        sentences = await asyncio.to_thread(speaker.speak_sync, text)
        for sentence in sentences:
            yield sentence
        return

    raise TypeError("Speaker must implement speak or speak_sync")


async def run_stage6_session(
    *,
    env_id: str,
    seed: int,
    fps: int,
    window_scale: int,
    subtitle_font: str,
    subtitle_size: int,
    subtitle_max_text_width: int,
    hud: bool,
    text_bands: bool,
    min_window_width: int,
    env_kwargs: dict[str, Any] | None,
    narrator: AsyncNarratorClient | NarratorClient,
    narration_interval_seconds: float,
    min_gap_seconds: float,
    reward_spike_threshold: float,
    pixel_delta_threshold: float,
    max_context_events: int,
    previous_narration_window: int,
    agent_kind: Literal["random", "scripted", "sb3"],
    sb3_repo_id: str | None,
    sb3_filename: str | None,
    trusted_repo_prefixes: list[str] | tuple[str, ...] = (
        DEFAULT_TRUSTED_SB3_REPO_PREFIXES
    ),
    enforce_trusted_repo: bool = False,
    voice_enabled: bool = False,
    tts_engine: Literal["kokoro", "xtts", "chatterbox"] = "kokoro",
    tts_voice: str = "bm_george",
    tts_speed: float = 0.95,
    tts_sample_rate: int = 24_000,
    speaker: AsyncSpeakerClient | SpeakerClient | None = None,
    audio_output: AudioOutputClient | None = None,
    max_steps: int | None = None,
    max_episodes: int | None = None,
    on_narration: Callable[[str, int, float], None] | None = None,
) -> Stage4RunResult:
    """Run Stage 6 async orchestration with keyframe selection and backpressure."""

    if narration_interval_seconds <= 0:
        raise ValueError("narration_interval_seconds must be positive")
    if min_gap_seconds < 0:
        raise ValueError("min_gap_seconds must be non-negative")
    if max_context_events <= 0:
        raise ValueError("max_context_events must be positive")
    if previous_narration_window <= 0:
        raise ValueError("previous_narration_window must be positive")
    if max_steps is not None and max_steps <= 0:
        raise ValueError("max_steps must be a positive integer when provided")
    if max_episodes is not None and max_episodes <= 0:
        raise ValueError("max_episodes must be a positive integer when provided")

    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    display = Display(
        env_id=env_id,
        fps=fps,
        window_scale=window_scale,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        subtitle_max_text_width=subtitle_max_text_width,
        hud=hud,
        text_bands=text_bands,
        min_window_width=min_window_width,
    )
    display.set_subtitle("A pause. The creature gathers itself.")

    random_agent = RandomAgent(env)
    scripted_agent = ScriptedAgent(env_id=env_id, fallback=random_agent)
    policy = None
    policy_disabled = False

    if agent_kind == "sb3":
        if sb3_repo_id is None or sb3_filename is None:
            raise ValueError("sb3_repo_id and sb3_filename are required for SB3 agent")
        policy = load_sb3_policy(
            repo_id=sb3_repo_id,
            filename=sb3_filename,
            trusted_repo_prefixes=trusted_repo_prefixes,
            enforce_trusted_repo=enforce_trusted_repo,
        )

    active_speaker = speaker
    active_audio_output = audio_output
    tts_active = voice_enabled

    if voice_enabled:
        try:
            if tts_engine != "kokoro":
                raise ValueError(
                    "Only 'kokoro' tts_engine is currently supported in Stage 6"
                )

            if active_audio_output is None:
                from docugym.audio import AudioOutput

                active_audio_output = AudioOutput(sample_rate=tts_sample_rate)

            if active_speaker is None:
                from docugym.tts import KokoroTTS

                active_speaker = KokoroTTS(
                    voice=tts_voice,
                    speed=tts_speed,
                    sample_rate=tts_sample_rate,
                )

            active_audio_output.start()
        except Exception as exc:
            logger.warning(
                "Voice mode unavailable; continuing subtitle-only narration: %s",
                exc,
            )
            tts_active = False

    frame_q: asyncio.Queue[_FrameEvent] = asyncio.Queue(maxsize=4)
    display_q: asyncio.Queue[_DisplayEvent] = asyncio.Queue(maxsize=4)
    narration_q: asyncio.Queue[_NarrationCandidate] = asyncio.Queue(maxsize=2)
    subtitle_q: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
    tts_q: asyncio.Queue[str] = asyncio.Queue(maxsize=2)

    stop_event = asyncio.Event()
    narration_sem = asyncio.Semaphore(1)
    tts_sem = asyncio.Semaphore(1)

    latency_samples_ms: list[float] = []
    narration_count = 0
    dropped_narration_candidates = 0
    rendered_steps = 0
    previous_narrations: deque[str] = deque(maxlen=previous_narration_window)
    recent_events: deque[str] = deque(maxlen=max_context_events)

    async def env_task() -> None:
        nonlocal rendered_steps, policy_disabled

        observation, _ = env.reset(seed=seed)
        step = 0
        episodes = 0
        episode_reward = 0.0

        while not stop_event.is_set():
            if policy is not None and not policy_disabled:
                try:
                    action, _ = policy.predict(observation, deterministic=True)
                except Exception as exc:  # pragma: no cover - runtime dependent
                    logger.warning(
                        "SB3 policy prediction failed, "
                        "falling back to random actions: %s",
                        exc,
                    )
                    policy_disabled = True
                    action = random_agent.act(observation)
            elif agent_kind == "scripted":
                action = scripted_agent.act(observation)
            else:
                action = random_agent.act(observation)

            observation, reward, terminated, truncated, _ = env.step(action)
            episode_reward += float(reward)
            frame = env.render()

            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            step += 1
            rendered_steps = step
            timestamp = perf_counter()
            frame_event = _FrameEvent(
                frame=frame,
                step=step,
                reward=float(reward),
                episode_reward=episode_reward,
                terminated=terminated,
                truncated=truncated,
                timestamp=timestamp,
            )

            _ = _push_drop_oldest(frame_q, frame_event)
            _ = _push_drop_oldest(
                display_q,
                _DisplayEvent(
                    frame=frame,
                    step=step,
                    episode_reward=episode_reward,
                ),
            )

            if max_steps is not None and step >= max_steps:
                stop_event.set()
                break

            if terminated or truncated:
                episodes += 1
                if max_episodes is not None and episodes >= max_episodes:
                    stop_event.set()
                    break
                observation, _ = env.reset()
                episode_reward = 0.0

            if not display.is_open:
                stop_event.set()
                break

            await asyncio.sleep(0)

    async def keyframe_task() -> None:
        nonlocal dropped_narration_candidates

        previous_frame: np.ndarray | None = None
        last_interval_ts = perf_counter()
        last_narration_ts = float("-inf")

        while not stop_event.is_set() or not frame_q.empty():
            try:
                frame_event = await asyncio.wait_for(frame_q.get(), timeout=0.1)
            except TimeoutError:
                continue

            reasons: list[str] = []
            now = frame_event.timestamp
            visual_delta: float | None = None

            if now - last_interval_ts >= narration_interval_seconds:
                reasons.append("cadence")
                last_interval_ts = now
            if abs(frame_event.reward) > reward_spike_threshold:
                reasons.append("reward_spike")
            if frame_event.terminated or frame_event.truncated:
                reasons.append("episode_boundary")
            if previous_frame is not None:
                visual_delta = _mean_abs_pixel_delta(frame_event.frame, previous_frame)
                if visual_delta > pixel_delta_threshold:
                    reasons.append("visual_delta")
            previous_frame = frame_event.frame

            if not reasons:
                continue
            if now - last_narration_ts < min_gap_seconds:
                continue

            delta_text = "n/a" if visual_delta is None else f"{visual_delta:.2f}"
            event_summary = (
                f"step {frame_event.step}; reward {frame_event.reward:+.2f}; "
                f"episode reward {frame_event.episode_reward:+.2f}; "
                f"delta {delta_text}; triggers {','.join(reasons)}"
            )
            recent_events.append(event_summary)

            dropped = _push_drop_oldest(
                narration_q,
                _NarrationCandidate(
                    frame=frame_event.frame,
                    step=frame_event.step,
                    event_summary=event_summary,
                    timestamp=now,
                ),
            )
            if dropped:
                dropped_narration_candidates += 1
                logger.info(
                    "Dropped stale narration candidate at step=%d due backlog",
                    frame_event.step,
                )
            else:
                last_narration_ts = now

            await asyncio.sleep(0)

    async def narrator_task() -> None:
        nonlocal narration_count, dropped_narration_candidates

        while not stop_event.is_set() or not narration_q.empty():
            try:
                candidate = await asyncio.wait_for(narration_q.get(), timeout=0.1)
            except TimeoutError:
                continue

            previous_text = " ".join(previous_narrations)
            context = NarrationContext(
                env_human_name=_env_human_name(env_id),
                previous_narration=previous_text,
                event_summary=" | ".join(recent_events),
            )

            started = perf_counter()
            try:
                async with narration_sem:
                    narration = await _narrate_async(
                        narrator=narrator,
                        frame=candidate.frame,
                        context=context,
                    )
            except Exception as exc:
                logger.warning(
                    "Narration request failed at step=%d: %s",
                    candidate.step,
                    exc,
                )
                narration = "A pause. The creature gathers itself."

            latency_ms = (perf_counter() - started) * 1000.0
            narration_count += 1
            latency_samples_ms.append(latency_ms)
            previous_narrations.append(narration)

            _ = _push_drop_oldest(subtitle_q, narration)

            if tts_active and active_speaker is not None:
                dropped_tts = _push_drop_oldest(tts_q, narration)
                if dropped_tts:
                    dropped_narration_candidates += 1
                    logger.info(
                        "Dropped queued narration text at step=%d due TTS backlog",
                        candidate.step,
                    )

            logger.info(
                "Narration[%d] step=%d latency_ms=%.1f text=%s",
                narration_count,
                candidate.step,
                latency_ms,
                narration,
            )
            if on_narration is not None:
                on_narration(narration, candidate.step, latency_ms)

            await asyncio.sleep(0)

    async def tts_task() -> None:
        if not tts_active or active_speaker is None or active_audio_output is None:
            return

        while not stop_event.is_set() or not tts_q.empty():
            try:
                text = await asyncio.wait_for(tts_q.get(), timeout=0.1)
            except TimeoutError:
                continue

            try:
                async with tts_sem:
                    async for sentence in _speak_async(active_speaker, text):
                        subtitle_text = sentence.graphemes.strip()
                        if subtitle_text:
                            _ = _push_drop_oldest(subtitle_q, subtitle_text)
                        for chunk in sentence.chunks:
                            active_audio_output.enqueue(chunk)
                        if stop_event.is_set():
                            break
            except Exception as exc:
                logger.warning(
                    "TTS synthesis failed; continuing subtitle-only: %s",
                    exc,
                )

            await asyncio.sleep(0)

    async def display_task() -> None:
        latest_display: _DisplayEvent | None = None

        while not stop_event.is_set():
            subtitle = _drain_latest(subtitle_q)
            if isinstance(subtitle, str):
                display.set_subtitle(subtitle)

            latest_display = _drain_latest(display_q, latest_display)
            if latest_display is None:
                await asyncio.sleep(0.01)
                continue

            display.set_status(
                step=latest_display.step,
                episode_reward=latest_display.episode_reward,
            )
            if not display.blit_frame(latest_display.frame):
                stop_event.set()
                break

            await asyncio.sleep(0)

    tasks = [
        asyncio.create_task(env_task(), name="env_task"),
        asyncio.create_task(keyframe_task(), name="keyframe_task"),
        asyncio.create_task(narrator_task(), name="narrator_task"),
        asyncio.create_task(tts_task(), name="tts_task"),
        asyncio.create_task(display_task(), name="display_task"),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        stop_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if tts_active and active_audio_output is not None:
            active_audio_output.stop()
        display.close()
        env.close()

    return Stage4RunResult(
        rendered_steps=rendered_steps,
        narration_count=narration_count,
        dropped_narration_candidates=dropped_narration_candidates,
        latency_p50_ms=_percentile(latency_samples_ms, 0.50),
        latency_p95_ms=_percentile(latency_samples_ms, 0.95),
    )


def run_stage6_session_sync(**kwargs: Any) -> Stage4RunResult:
    """Synchronous wrapper around the async Stage 6 runtime pipeline."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_stage6_session(**kwargs))

    raise RuntimeError(
        "run_stage6_session_sync cannot run from an active event loop; "
        "await run_stage6_session instead."
    )
