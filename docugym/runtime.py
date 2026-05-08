"""Async orchestration entrypoint for narrated DocuGym sessions.

This module coordinates environment stepping, keyframe selection, VLM narration,
optional TTS playback, display rendering, and optional MP4 recording in a bounded
queue pipeline that prefers fresh gameplay over stale narration work.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import inspect
import logging
import math
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Literal,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np

from docugym.clips import save_clip_snapshot
from docugym.display import Display
from docugym.display_actions import build_action_transitions, poll_display_actions
from docugym.env import (
    DEFAULT_TRUSTED_SB3_REPO_PREFIXES,
    RandomAgent,
    ScriptedAgent,
    load_sb3_policy,
    make_env,
)
from docugym.keyframes import KeyframeSelector
from docugym.narration_defaults import (
    DEFAULT_NARRATION_TEXT,
    validate_narration_config,
)
from docugym.narration_events import (
    format_event_summary,
    humanize_env_id,
    join_previous_narrations,
    join_recent_events,
)
from docugym.narrator import NarrationContext
from docugym.queue_utils import (
    clear_async_queue,
    drain_latest_async,
    push_drop_oldest_async,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class RunResult:
    """Aggregated metrics returned from :func:`run_session`.

    Attributes:
        rendered_steps: Total number of rendered environment steps.
        narration_count: Number of narration requests processed.
        latency_p50_ms: Median narration latency in milliseconds.
        latency_p95_ms: 95th percentile narration latency in milliseconds.
        dropped_narration_candidates: Combined dropped keyframe/TTS inputs.
        dropped_keyframe_candidates: Number of keyframe candidates dropped due to
            narration queue pressure.
        dropped_tts_inputs: Number of narration texts dropped before TTS synthesis.
        narration_failures: Number of narration requests that failed and fell back.
        recording_failed: Whether recording was disabled after a recorder failure.
    """

    rendered_steps: int
    narration_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    dropped_narration_candidates: int = 0
    dropped_keyframe_candidates: int = 0
    dropped_tts_inputs: int = 0
    narration_failures: int = 0
    recording_failed: bool = False


@dataclass(slots=True)
class _FrameEvent:
    """Frame metadata emitted by the environment producer task.

    Runtime producers make frames contiguous and read-only before fan-out so
    selector, display, and recording consumers never observe a mutated env buffer.
    """

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
    """Async narrator contract consumed by the runtime pipeline.

    Runtime adapters use this protocol to accept custom narrator implementations
    without binding to one concrete client class.
    """

    async def narrate_frame(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a selected keyframe.

        Args:
            frame: Selected RGB/RGBA frame.
            context: Continuity/context payload for prompt construction.

        Returns:
            Narration text for display and optional TTS.
        """


@runtime_checkable
class AsyncSpeakerClient(Protocol):
    """Async speaker contract for sentence-level speech synthesis.

    Implementations are expected to stream sentence outputs so subtitles and audio
    playback can progress incrementally.
    """

    def speak(self, text: str) -> AsyncIterator[SpeechSentence]:
        """Yield sentence-level speech outputs for a narration text.

        Args:
            text: Narration text to synthesize.

        Returns:
            Async iterator of sentence outputs with text+audio chunks.
        """


@runtime_checkable
class NarratorClient(Protocol):
    """Structural narrator type for synchronous narration clients.

    Used when narration work is delegated to background threads.
    """

    def narrate_frame_sync(self, frame: np.ndarray, context: NarrationContext) -> str:
        """Return narration text for a given frame and context.

        Args:
            frame: Selected RGB/RGBA frame.
            context: Continuity/context payload for prompt construction.

        Returns:
            Narration text for display and optional TTS.
        """


class SpeechSentence(Protocol):
    """Sentence-level TTS output used for subtitle and audio streaming.

    Attributes:
        graphemes: Subtitle text for this spoken sentence.
        chunks: Audio chunks for this sentence in playback order.
    """

    graphemes: str
    chunks: list[np.ndarray]


@runtime_checkable
class SpeakerClient(Protocol):
    """Synchronous speaker contract used by non-async runtime paths.

    Implementations return full sentence output sequences at once.
    """

    def speak_sync(self, text: str) -> Sequence[SpeechSentence]:
        """Synthesize sentence-level audio chunks for narration text.

        Args:
            text: Narration text to synthesize.

        Returns:
            Sequence of sentence outputs with text+audio chunks.
        """


@runtime_checkable
class AudioOutputClient(Protocol):
    """Audio output sink contract used by runtime playback integration.

    Runtime code uses this abstraction to support alternate audio backends.
    """

    def start(self) -> None:
        """Start the audio callback stream.

        Called once before the runtime begins enqueueing speech chunks.
        """

    def enqueue(self, chunk: np.ndarray) -> None:
        """Queue one mono float32 chunk for playback.

        Args:
            chunk: One chunk of synthesized mono audio samples.
        """

    def stop(self) -> None:
        """Stop and release audio stream resources.

        Called during runtime teardown to release backend handles.
        """


@runtime_checkable
class SessionRecorderClient(Protocol):
    """Recorder sink contract used by runtime recording integration.

    Implementations accept frame/audio streams and finalize optional artifacts.
    """

    def write_video_frame(self, frame: np.ndarray) -> None:
        """Append one rendered frame to the recording stream.

        Args:
            frame: RGB/RGBA frame to append.
        """

    def write_audio_chunk(self, chunk: np.ndarray, *, timestamp: float) -> None:
        """Append one synthesized chunk at a monotonic timestamp.

        Args:
            chunk: Mono audio samples.
            timestamp: Monotonic timestamp associated with chunk emission.
        """

    def close(self, *, end_timestamp: float) -> Path | None:
        """Finalize recording artifacts and return saved output path.

        Args:
            end_timestamp: Monotonic timestamp marking session end.

        Returns:
            Output path when artifacts were saved; otherwise ``None``.
        """


def _percentile_sorted(ordered: Sequence[float], quantile: float) -> float | None:
    """Return one linearly interpolated quantile from sorted values.

    The caller is expected to provide data already sorted in ascending order. The
    function uses linear interpolation between adjacent ranks so small sample sets
    produce stable percentile estimates instead of abrupt jumps.
    """

    if not ordered:
        return None
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


def _percentiles(
    values: Sequence[float], quantiles: Sequence[float]
) -> list[float | None]:
    """Compute several quantiles with one shared sort pass."""

    if not values:
        return [None for _ in quantiles]

    ordered = sorted(values)
    return [_percentile_sorted(ordered, quantile) for quantile in quantiles]


def _set_display_flag(display: Any, method_name: str, value: bool) -> None:
    """Call an optional display mutator when the method exists."""

    method = getattr(display, method_name, None)
    if callable(method):
        method(value)


def _clear_audio_buffer(audio_output: AudioOutputClient) -> None:
    """Flush buffered audio only when the backend exposes a clear hook."""

    clear = getattr(audio_output, "clear", None)
    if callable(clear):
        clear()


async def _narrate_async(
    narrator: AsyncNarratorClient | NarratorClient,
    frame: np.ndarray,
    context: NarrationContext,
) -> str:
    """Dispatch narration to either async or sync narrator implementations.

    Runtime code uses this adapter to keep one async call site while still
    accepting synchronous narrator clients. Sync narrators are moved to a worker
    thread so the event loop remains responsive during network or model latency.

    Raises:
        TypeError: If ``narrator`` does not implement either expected protocol.
    """

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
    """Yield sentence-level TTS results from async or sync speaker clients.

    This normalizes both speaker styles into one async iterator so downstream
    subtitle/audio streaming code does not branch on implementation type.

    Raises:
        TypeError: If ``speaker`` does not implement either expected protocol.
    """

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


async def _queue_get_until_stop(
    queue_obj: asyncio.Queue[Any],
    stop_event: asyncio.Event,
) -> Any | None:
    """Wait for queued work while still respecting cooperative shutdown.

    The function races ``queue.get()`` against ``stop_event.wait()`` so consumer
    tasks can terminate promptly when shutdown starts instead of hanging on an
    empty queue.
    """

    if not queue_obj.empty():
        return await queue_obj.get()

    get_task = asyncio.create_task(queue_obj.get())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {get_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    if get_task in done:
        return get_task.result()
    return None


async def _maybe_call_async_close(client: object) -> None:
    """Await an ``aclose`` hook when present, ignoring non-async objects."""

    close = getattr(client, "aclose", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


async def run_session(
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
    sb3_algorithm: str | None = None,
    sb3_device: str = "cpu",
    trusted_repo_prefixes: Sequence[str] | None = DEFAULT_TRUSTED_SB3_REPO_PREFIXES,
    enforce_trusted_repo: bool = True,
    sb3_revision: str | None = None,
    voice_enabled: bool = False,
    tts_engine: Literal["kokoro", "xtts", "chatterbox"] = "kokoro",
    tts_voice: str = "bm_george",
    tts_speed: float = 0.95,
    tts_sample_rate: int = 24_000,
    speaker: AsyncSpeakerClient | SpeakerClient | None = None,
    audio_output: AudioOutputClient | None = None,
    record_out_path: Path | None = None,
    recorder: SessionRecorderClient | None = None,
    ffmpeg_binary: str = "ffmpeg",
    max_steps: int | None = None,
    max_episodes: int | None = None,
    on_narration: Callable[[str, int, float], None] | None = None,
) -> RunResult:
    """Run one narrated gameplay session on the canonical async pipeline.

    The runtime is designed to keep gameplay smooth under load by using bounded
    queues and drop-oldest semantics for narration work. When voice output is
    enabled, subtitle ownership shifts to sentence-level TTS output so on-screen
    text follows spoken chunks instead of full-paragraph narration blocks.

    Args:
        env_id: Gymnasium environment id (for example ``ALE/SpaceInvaders-v5``).
        seed: Seed used for environment reset and action-space determinism.
        fps: Target display framerate.
        window_scale: Integer scaling factor for rendered frames.
        subtitle_font: Font name used for subtitle and HUD rendering.
        subtitle_size: Base subtitle font size in pixels.
        subtitle_max_text_width: Maximum subtitle wrapping width in pixels.
        hud: Whether to render the status bar.
        text_bands: Whether to reserve dedicated text bands outside gameplay.
        min_window_width: Minimum window width used for narrow environments.
        env_kwargs: Extra kwargs forwarded to ``gym.make``.
        narrator: Narrator client implementing async or sync narration protocol.
        narration_interval_seconds: Baseline cadence trigger interval.
        min_gap_seconds: Cooldown between accepted narration events.
        reward_spike_threshold: Absolute reward threshold that forces narration.
        pixel_delta_threshold: Visual delta threshold that forces narration.
        max_context_events: Number of recent event summaries retained in context.
        previous_narration_window: Number of prior narrations kept for continuity.
        agent_kind: Action source (``random``, ``scripted``, or ``sb3``).
        sb3_repo_id: Hugging Face repo id for SB3 policy loading.
        sb3_filename: SB3 policy artifact filename.
        sb3_algorithm: Optional explicit SB3 algorithm override.
        sb3_device: Torch device string used by SB3 policy loading.
        trusted_repo_prefixes: Allowed SB3 repo prefixes for trust enforcement.
        enforce_trusted_repo: Whether untrusted SB3 repos raise instead of warn.
        sb3_revision: Optional Hugging Face revision pin for SB3 artifacts.
        voice_enabled: Whether narration should be synthesized to audio.
        tts_engine: TTS backend selector (currently ``kokoro`` only).
        tts_voice: Kokoro voice id.
        tts_speed: Kokoro speaking-rate multiplier.
        tts_sample_rate: Audio sample rate for playback/recording alignment.
        speaker: Optional injected speaker implementation.
        audio_output: Optional injected audio output sink.
        record_out_path: Optional MP4 output path to enable recording.
        recorder: Optional injected session recorder.
        ffmpeg_binary: FFmpeg executable name/path used when recorder is created.
        max_steps: Optional hard cap on rendered steps.
        max_episodes: Optional hard cap on completed episodes.
        on_narration: Optional callback invoked per narration output.

    Returns:
        Aggregated counters and latency percentiles from the session.

    Raises:
        ValueError: If validation of cadence limits, SB3 options, or bounds fails.
        TypeError: If rendered frames are not numpy arrays in RGB-array mode.

    Example:
        result = await run_session(
            env_id="ALE/SpaceInvaders-v5",
            seed=42,
            fps=60,
            window_scale=3,
            subtitle_font="DejaVu Sans",
            subtitle_size=22,
            subtitle_max_text_width=960,
            hud=True,
            text_bands=True,
            min_window_width=960,
            env_kwargs=None,
            narrator=my_narrator,
            narration_interval_seconds=3.0,
            min_gap_seconds=1.5,
            reward_spike_threshold=5.0,
            pixel_delta_threshold=8.0,
            max_context_events=3,
            previous_narration_window=2,
            agent_kind="random",
            sb3_repo_id=None,
            sb3_filename=None,
        )
    """

    validate_narration_config(
        narration_interval_seconds=narration_interval_seconds,
        min_gap_seconds=min_gap_seconds,
        max_context_events=max_context_events,
        previous_narration_window=previous_narration_window,
    )
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
    display.set_subtitle(DEFAULT_NARRATION_TEXT)
    _set_display_flag(display, "set_narrating", False)

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
            revision=sb3_revision,
            algorithm=sb3_algorithm,
            device=sb3_device,
        )

    active_speaker = speaker
    active_audio_output = audio_output
    active_recorder = recorder
    tts_active = voice_enabled

    if active_recorder is None and record_out_path is not None:
        from docugym.recording import FFmpegSessionRecorder

        active_recorder = FFmpegSessionRecorder(
            out_path=record_out_path,
            fps=fps,
            sample_rate=tts_sample_rate,
            ffmpeg_binary=ffmpeg_binary,
        )

    if voice_enabled:
        try:
            if tts_engine != "kokoro":
                raise ValueError("Only 'kokoro' tts_engine is currently supported")

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
    pause_event = asyncio.Event()
    pause_event.set()

    latency_samples_ms: deque[float] = deque(maxlen=256)
    narration_count = 0
    dropped_keyframe_candidates = 0
    dropped_tts_inputs = 0
    narration_failures = 0
    recording_failed = False
    rendered_steps = 0
    paused = False
    audio_muted = not tts_active
    latest_narration_text = DEFAULT_NARRATION_TEXT
    previous_narrations: deque[str] = deque(maxlen=previous_narration_window)
    recent_events: deque[str] = deque(maxlen=max_context_events)
    _set_display_flag(display, "set_paused", paused)
    _set_display_flag(display, "set_muted", audio_muted)

    async def env_task() -> None:
        nonlocal rendered_steps, policy_disabled, paused

        observation, _ = env.reset(seed=seed)
        step = 0
        episodes = 0
        episode_reward = 0.0

        while not stop_event.is_set():
            await pause_event.wait()

            if policy is not None and not policy_disabled:
                try:
                    action, _ = policy.predict(observation, deterministic=True)
                except Exception as exc:  # pragma: no cover - runtime dependent
                    logger.warning(
                        "SB3 policy prediction failed, "
                        "falling back to random actions: %s",
                        exc,
                        exc_info=True,
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
            frame = np.ascontiguousarray(frame)
            frame.flags.writeable = False

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

            _ = push_drop_oldest_async(frame_q, frame_event)
            _ = push_drop_oldest_async(
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
        nonlocal dropped_keyframe_candidates

        selector = KeyframeSelector(
            interval_seconds=narration_interval_seconds,
            min_gap_seconds=min_gap_seconds,
            reward_spike_threshold=reward_spike_threshold,
            pixel_delta_threshold=pixel_delta_threshold,
        )

        while not stop_event.is_set() or not frame_q.empty():
            frame_event = await _queue_get_until_stop(frame_q, stop_event)
            if frame_event is None:
                continue

            now = frame_event.timestamp
            decision = selector.consider(
                frame=frame_event.frame,
                reward=frame_event.reward,
                terminated=frame_event.terminated,
                truncated=frame_event.truncated,
                timestamp=now,
            )
            if decision is None:
                continue

            event_summary = format_event_summary(
                step=frame_event.step,
                reward=frame_event.reward,
                episode_reward=frame_event.episode_reward,
                visual_delta=decision.visual_delta,
                triggers=decision.reasons,
            )
            recent_events.append(event_summary)

            dropped = push_drop_oldest_async(
                narration_q,
                _NarrationCandidate(
                    frame=frame_event.frame,
                    step=frame_event.step,
                    event_summary=event_summary,
                    timestamp=now,
                ),
            )
            if dropped:
                dropped_keyframe_candidates += 1
                logger.info(
                    "Dropped stale narration candidate at step=%d due backlog",
                    frame_event.step,
                )
            else:
                selector.mark_narration_enqueued(timestamp=now)

            await asyncio.sleep(0)

    async def narrator_task() -> None:
        nonlocal narration_count, dropped_tts_inputs, latest_narration_text
        nonlocal narration_failures

        while not stop_event.is_set() or not narration_q.empty():
            candidate = await _queue_get_until_stop(narration_q, stop_event)
            if candidate is None:
                continue

            previous_text = join_previous_narrations(previous_narrations)
            context = NarrationContext(
                env_human_name=humanize_env_id(env_id),
                previous_narration=previous_text,
                event_summary=join_recent_events(recent_events),
            )

            started = perf_counter()
            try:
                narration = await _narrate_async(
                    narrator=narrator,
                    frame=candidate.frame,
                    context=context,
                )
            except Exception as exc:
                narration_failures += 1
                logger.warning(
                    "Narration request failed at step=%d: %s",
                    candidate.step,
                    exc,
                    exc_info=True,
                )
                narration = DEFAULT_NARRATION_TEXT

            latency_ms = (perf_counter() - started) * 1000.0
            narration_count += 1
            latency_samples_ms.append(latency_ms)
            previous_narrations.append(narration)
            latest_narration_text = narration

            tts_can_own_subtitles = (
                tts_active and active_speaker is not None and not audio_muted
            )
            if not tts_can_own_subtitles:
                _ = push_drop_oldest_async(subtitle_q, narration)

            if tts_can_own_subtitles:
                dropped_tts = push_drop_oldest_async(tts_q, narration)
                if dropped_tts:
                    dropped_tts_inputs += 1
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
                try:
                    await asyncio.to_thread(
                        on_narration,
                        narration,
                        candidate.step,
                        latency_ms,
                    )
                except Exception as exc:  # pragma: no cover - user callback path
                    logger.warning(
                        "Ignoring on_narration callback failure: %s",
                        exc,
                        exc_info=True,
                    )

            await asyncio.sleep(0)

    async def tts_task() -> None:
        nonlocal active_recorder, audio_muted, recording_failed

        if not tts_active or active_speaker is None or active_audio_output is None:
            return

        while not stop_event.is_set() or not tts_q.empty():
            text = await _queue_get_until_stop(tts_q, stop_event)
            if text is None:
                continue

            try:
                if audio_muted:
                    continue

                _set_display_flag(display, "set_narrating", True)
                async for sentence in _speak_async(active_speaker, text):
                    if audio_muted:
                        break

                    subtitle_text = sentence.graphemes.strip()
                    if subtitle_text:
                        _ = push_drop_oldest_async(subtitle_q, subtitle_text)
                    for chunk in sentence.chunks:
                        active_audio_output.enqueue(chunk)
                        if active_recorder is not None:
                            try:
                                active_recorder.write_audio_chunk(
                                    chunk,
                                    timestamp=perf_counter(),
                                )
                            except Exception as exc:
                                recording_failed = True
                                logger.warning(
                                    "Disabling recording after audio failure: %s",
                                    exc,
                                    exc_info=True,
                                )
                                active_recorder = None
                    if stop_event.is_set():
                        break
            except Exception as exc:
                logger.warning(
                    "TTS synthesis failed; continuing subtitle-only: %s",
                    exc,
                    exc_info=True,
                )
            finally:
                _set_display_flag(display, "set_narrating", False)

            await asyncio.sleep(0)

    async def display_task() -> None:
        nonlocal active_recorder, paused, audio_muted, dropped_keyframe_candidates
        nonlocal recording_failed

        latest_display: _DisplayEvent | None = None

        while not stop_event.is_set():
            subtitle = drain_latest_async(subtitle_q)
            if isinstance(subtitle, str):
                display.set_subtitle(subtitle)

            latest_display = drain_latest_async(display_q, latest_display)
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

            if active_recorder is not None:
                try:
                    active_recorder.write_video_frame(latest_display.frame)
                except Exception as exc:
                    recording_failed = True
                    logger.warning(
                        "Disabling recording after video write failure: %s",
                        exc,
                        exc_info=True,
                    )
                    active_recorder = None

            actions = poll_display_actions(display)
            for transition in build_action_transitions(
                actions,
                paused=paused,
                muted=audio_muted,
            ):
                action = transition.action
                if action == "toggle_pause":
                    paused = transition.paused
                    _set_display_flag(display, "set_paused", paused)
                    if paused:
                        pause_event.clear()
                    else:
                        pause_event.set()
                    logger.info("Playback pause toggled: paused=%s", paused)
                    continue

                if action == "toggle_mute":
                    audio_muted = transition.muted
                    _set_display_flag(display, "set_muted", audio_muted)
                    if audio_muted:
                        clear_async_queue(tts_q)
                        if active_audio_output is not None:
                            _clear_audio_buffer(active_audio_output)
                    logger.info("Playback mute toggled: muted=%s", audio_muted)
                    continue

                if action == "force_narrate":
                    event_summary = format_event_summary(
                        step=latest_display.step,
                        reward=None,
                        episode_reward=latest_display.episode_reward,
                        visual_delta=None,
                        triggers=["manual"],
                    )
                    recent_events.append(event_summary)
                    dropped = push_drop_oldest_async(
                        narration_q,
                        _NarrationCandidate(
                            frame=latest_display.frame,
                            step=latest_display.step,
                            event_summary=event_summary,
                            timestamp=perf_counter(),
                        ),
                    )
                    if dropped:
                        dropped_keyframe_candidates += 1
                        logger.info(
                            "Dropped forced narration candidate at step=%d due backlog",
                            latest_display.step,
                        )
                    continue

                if action == "save_clip":
                    frame_copy = np.array(latest_display.frame, copy=True)
                    try:
                        frame_path, narration_path = await asyncio.to_thread(
                            save_clip_snapshot,
                            frame=frame_copy,
                            step=latest_display.step,
                            narration=latest_narration_text,
                        )
                        logger.info(
                            "Saved clip snapshot: frame=%s narration=%s",
                            frame_path,
                            narration_path,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to save clip snapshot: %s",
                            exc,
                            exc_info=True,
                        )

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
        pause_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        end_ts = perf_counter()
        if tts_active and active_audio_output is not None:
            active_audio_output.stop()
        if active_recorder is not None:
            try:
                saved_path = active_recorder.close(end_timestamp=end_ts)
                if saved_path is None:
                    logger.info("Recording discarded because no frames were rendered")
            except Exception as exc:
                recording_failed = True
                logger.warning("Failed to finalize recording: %s", exc, exc_info=True)
        await _maybe_call_async_close(narrator)
        display.close()
        env.close()

    latency_p50_ms, latency_p95_ms = _percentiles(latency_samples_ms, (0.50, 0.95))
    dropped_narration_candidates = dropped_keyframe_candidates + dropped_tts_inputs
    return RunResult(
        rendered_steps=rendered_steps,
        narration_count=narration_count,
        dropped_narration_candidates=dropped_narration_candidates,
        dropped_keyframe_candidates=dropped_keyframe_candidates,
        dropped_tts_inputs=dropped_tts_inputs,
        narration_failures=narration_failures,
        recording_failed=recording_failed,
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
    )


def run_session_sync(**kwargs: Any) -> RunResult:
    """Run :func:`run_session` from synchronous call sites.

    This helper exists for CLI and wrapper integration points that are not running
    an event loop. It intentionally fails fast inside active loops to avoid nested
    loop bugs and to push async callers toward ``await run_session(...)``.

    Args:
        **kwargs: Keyword arguments forwarded directly to :func:`run_session`.

    Returns:
        Aggregated run metrics produced by :func:`run_session`.

    Raises:
        RuntimeError: If called while an event loop is already running.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_session(**kwargs))

    raise RuntimeError(
        "run_session_sync cannot run from an active event loop; "
        "await run_session instead."
    )
