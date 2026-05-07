"""PyGame rendering utilities for gameplay frames and narration overlays.

This module is shared by both async runtime and wrapper modes so keyboard controls,
subtitle rendering policy, and HUD status formatting remain behaviorally aligned.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pygame

from docugym.env import RandomAgent, make_env

DisplayAction = Literal[
    "toggle_pause",
    "force_narrate",
    "toggle_mute",
    "save_clip",
]


class Display:
    """Render gameplay frames with HUD/subtitle overlays and keyboard actions.

    The class owns all PyGame lifecycle state and exposes lightweight mutators so
    orchestration code can push latest status/subtitle text without managing SDL
    details directly.

    This type intentionally centralizes keyboard-action mapping so runtime and
    wrapper orchestration paths stay behaviorally aligned.
    """

    def __init__(
        self,
        env_id: str,
        fps: int = 60,
        window_scale: int = 3,
        subtitle_font: str = "DejaVu Sans",
        subtitle_size: int = 22,
        hud: bool = True,
        text_bands: bool = True,
        min_window_width: int = 960,
        subtitle_max_text_width: int = 960,
    ) -> None:
        """Initialize a PyGame window manager for narrated frame rendering.

        Args:
            env_id: Environment identifier shown in HUD text.
            fps: Target render framerate.
            window_scale: Integer scaling factor applied to raw frame dimensions.
            subtitle_font: Font family used for subtitle and HUD text.
            subtitle_size: Base subtitle font size in pixels.
            hud: Whether to render the status HUD.
            text_bands: Whether HUD/subtitle text uses dedicated top/bottom bands.
            min_window_width: Minimum display width; narrow frames are centered.
            subtitle_max_text_width: Maximum subtitle wrapping width in pixels.

        Raises:
            ValueError: If FPS or sizing parameters are non-positive.
        """

        if fps <= 0:
            raise ValueError("fps must be a positive integer")
        if window_scale <= 0:
            raise ValueError("window_scale must be a positive integer")
        if min_window_width <= 0:
            raise ValueError("min_window_width must be a positive integer")
        if subtitle_max_text_width <= 0:
            raise ValueError("subtitle_max_text_width must be a positive integer")

        self._env_id = env_id
        self._fps = fps
        self._window_scale = window_scale
        self._hud = hud
        self._text_bands = text_bands
        self._min_window_width = min_window_width
        self._subtitle_max_text_width = subtitle_max_text_width
        self._subtitle_max_lines = 2

        self._subtitle = ""
        self._step = 0
        self._episode_reward = 0.0
        self._narrating = False
        self._paused = False
        self._muted = False
        self._is_open = True
        self._pending_actions: list[DisplayAction] = []

        self._window: pygame.Surface | None = None
        self._render_size: tuple[int, int] | None = None
        self._clock = pygame.time.Clock()

        pygame.init()
        pygame.font.init()
        pygame.display.set_caption(f"DocuGym - {env_id}")

        self._subtitle_font = pygame.font.SysFont(subtitle_font, subtitle_size)
        self._hud_font = pygame.font.SysFont(subtitle_font, max(14, subtitle_size - 6))

    @property
    def is_open(self) -> bool:
        """Return whether the display loop is still active.

        Returns:
            ``True`` while the display window remains open.
        """

        return self._is_open

    def close(self) -> None:
        """Close the display and release PyGame resources.

        Safe to call from shutdown paths where the window might already be closed.
        """

        self._is_open = False
        pygame.display.quit()
        pygame.quit()

    def set_subtitle(self, text: str) -> None:
        """Set the current subtitle text.

        Args:
            text: Subtitle content to render on the next frame.
        """

        self._subtitle = text.strip()

    def set_status(self, step: int, episode_reward: float) -> None:
        """Update HUD status values.

        Args:
            step: Current global environment step.
            episode_reward: Accumulated reward within the current episode.
        """

        self._step = step
        self._episode_reward = episode_reward

    def set_narrating(self, active: bool) -> None:
        """Update HUD narration-activity indicator.

        Args:
            active: Whether narration/TTS is currently active.
        """

        self._narrating = active

    def set_paused(self, paused: bool) -> None:
        """Update HUD pause indicator.

        Args:
            paused: Whether playback is currently paused.
        """

        self._paused = paused

    def set_muted(self, muted: bool) -> None:
        """Update HUD audio-muted indicator.

        Args:
            muted: Whether audio output should be shown as muted.
        """

        self._muted = muted

    def poll_actions(self) -> list[DisplayAction]:
        """Return and clear pending keyboard-triggered actions.

        Returns:
            FIFO-ordered list of display actions since the last poll.
        """

        actions = list(self._pending_actions)
        self._pending_actions.clear()
        return actions

    def blit_frame(self, frame: np.ndarray) -> bool:
        """Render one frame plus overlays, then pace to configured FPS.

        Returns ``False`` when the window has been closed so callers can terminate
        their loop without additional event polling.

        Args:
            frame: Environment RGB/RGBA frame with shape ``(H, W, C)``.

        Returns:
            ``True`` while the window remains open; otherwise ``False``.

        Raises:
            ValueError: If frame dimensionality or channels are invalid.
        """

        if not self._is_open:
            return False

        self._handle_events()
        if not self._is_open:
            return False

        normalized_frame = self._normalize_frame(frame)
        frame_height, frame_width, _ = normalized_frame.shape
        frame_render_size = (
            frame_width * self._window_scale,
            frame_height * self._window_scale,
        )
        hud_band_height = (
            self._status_bar_height() if self._hud and self._text_bands else 0
        )
        subtitle_band_height = (
            self._subtitle_band_height() if self._subtitle and self._text_bands else 0
        )
        window_size, frame_offset = self._compute_window_layout(
            frame_render_size=frame_render_size,
            min_window_width=self._min_window_width,
            hud_enabled=self._hud,
            text_bands=self._text_bands,
            subtitle_present=bool(self._subtitle),
            hud_band_height=hud_band_height,
            subtitle_band_height=subtitle_band_height,
        )
        frame_offset_x, frame_offset_y = frame_offset

        if self._window is None or self._render_size != window_size:
            self._window = pygame.display.set_mode(window_size)
            self._render_size = window_size

        transposed = np.transpose(normalized_frame, (1, 0, 2))
        frame_surface = pygame.surfarray.make_surface(transposed)
        if self._window_scale != 1:
            frame_surface = pygame.transform.scale(frame_surface, frame_render_size)

        self._window.fill((0, 0, 0))
        self._window.blit(frame_surface, (frame_offset_x, frame_offset_y))
        if self._hud:
            self._draw_status_bar(y=0, band_height=hud_band_height)
        if self._subtitle:
            if self._text_bands:
                subtitle_y = frame_offset_y + frame_render_size[1]
                self._draw_subtitle_band(y=subtitle_y, band_height=subtitle_band_height)
            else:
                self._draw_subtitle_card()

        pygame.display.flip()
        self._clock.tick(self._fps)
        return self._is_open

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._is_open = False
                return

            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_ESCAPE:
                self._is_open = False
                return

            action = self._key_to_action(event.key)
            if action is not None:
                self._pending_actions.append(action)

    def _draw_status_bar(self, y: int, band_height: int = 0) -> None:
        if self._window is None:
            return

        width = self._window.get_width()
        text = self._build_status_text(
            env_id=self._env_id,
            step=self._step,
            episode_reward=self._episode_reward,
            narrating=self._narrating,
            paused=self._paused,
            muted=self._muted,
        )
        text_surface = self._hud_font.render(text, True, (245, 245, 245))
        bar_height = band_height or self._status_bar_height()
        bar_alpha = 255 if self._text_bands else 180

        bar = pygame.Surface((width, bar_height), pygame.SRCALPHA)
        bar.fill((0, 0, 0, bar_alpha))
        self._window.blit(bar, (0, y))

        text_y = y + (bar_height - text_surface.get_height()) // 2
        self._window.blit(text_surface, (8, text_y))

    def _status_bar_height(self) -> int:
        return self._hud_font.get_linesize() + 12

    def _subtitle_band_height(self) -> int:
        return self._subtitle_font.get_linesize() * self._subtitle_max_lines + 24

    @staticmethod
    def _build_status_text(
        *,
        env_id: str,
        step: int,
        episode_reward: float,
        narrating: bool,
        paused: bool,
        muted: bool,
    ) -> str:
        narration_state = "narrating" if narrating else "idle"
        run_state = "paused" if paused else "running"
        audio_state = "muted" if muted else "audible"
        return (
            f"env: {env_id} | step: {step} | episode reward: {episode_reward:.2f} "
            f"| {narration_state} | {run_state} | audio: {audio_state}"
        )

    @staticmethod
    def _key_to_action(key: int) -> DisplayAction | None:
        if key == pygame.K_SPACE:
            return "toggle_pause"
        if key == pygame.K_n:
            return "force_narrate"
        if key == pygame.K_m:
            return "toggle_mute"
        if key == pygame.K_s:
            return "save_clip"
        return None

    @staticmethod
    def _compute_window_layout(
        frame_render_size: tuple[int, int],
        *,
        min_window_width: int,
        hud_enabled: bool,
        text_bands: bool,
        subtitle_present: bool,
        hud_band_height: int,
        subtitle_band_height: int,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        frame_width, frame_height = frame_render_size
        window_width = max(frame_width, min_window_width)
        window_height = frame_height
        frame_offset_y = 0

        if text_bands:
            if hud_enabled:
                window_height += hud_band_height
                frame_offset_y = hud_band_height
            if subtitle_present:
                window_height += subtitle_band_height

        frame_offset_x = (window_width - frame_width) // 2
        return (window_width, window_height), (frame_offset_x, frame_offset_y)

    @staticmethod
    def _compute_subtitle_wrap_width(
        window_width: int,
        horizontal_margin: int,
        subtitle_max_text_width: int,
    ) -> int:
        usable_width = max(40, window_width - horizontal_margin)
        return min(usable_width, subtitle_max_text_width)

    def _draw_subtitle_band(self, y: int, band_height: int) -> None:
        if self._window is None:
            return

        width = self._window.get_width()
        band = pygame.Surface((width, band_height), pygame.SRCALPHA)
        band.fill((0, 0, 0, 255))
        self._window.blit(band, (0, y))

        lines = self._wrap_text(
            text=self._subtitle,
            font=self._subtitle_font,
            max_width=self._compute_subtitle_wrap_width(
                window_width=width,
                horizontal_margin=24,
                subtitle_max_text_width=self._subtitle_max_text_width,
            ),
            max_lines=self._subtitle_max_lines,
        )
        if not lines:
            return

        rendered_lines = [
            self._subtitle_font.render(line, True, (255, 255, 255)) for line in lines
        ]
        line_height = max(line.get_height() for line in rendered_lines)
        total_text_height = line_height * len(rendered_lines)
        y_offset = y + (band_height - total_text_height) // 2

        for line in rendered_lines:
            x_offset = (width - line.get_width()) // 2
            self._window.blit(line, (x_offset, y_offset))
            y_offset += line_height

    def _draw_subtitle_card(self) -> None:
        if self._window is None:
            return

        lines = self._wrap_text(
            text=self._subtitle,
            font=self._subtitle_font,
            max_width=self._compute_subtitle_wrap_width(
                window_width=self._window.get_width(),
                horizontal_margin=48,
                subtitle_max_text_width=self._subtitle_max_text_width,
            ),
            max_lines=self._subtitle_max_lines,
        )
        if not lines:
            return

        rendered_lines = [
            self._subtitle_font.render(line, True, (255, 255, 255)) for line in lines
        ]
        line_height = max(line.get_height() for line in rendered_lines)
        card_padding = 12
        card_width = max(line.get_width() for line in rendered_lines) + card_padding * 2
        card_height = line_height * len(rendered_lines) + card_padding * 2

        card_surface = pygame.Surface((card_width, card_height), pygame.SRCALPHA)
        card_surface.fill((0, 0, 0, 170))

        y_offset = card_padding
        for line in rendered_lines:
            x_offset = (card_width - line.get_width()) // 2
            card_surface.blit(line, (x_offset, y_offset))
            y_offset += line_height

        card_x = (self._window.get_width() - card_width) // 2
        card_y = self._window.get_height() - card_height - 12
        self._window.blit(card_surface, (card_x, card_y))

    @staticmethod
    def _normalize_frame(frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 3:
            raise ValueError(f"Expected frame with 3 dims (H, W, C), got {frame.shape}")

        if frame.shape[2] not in {3, 4}:
            raise ValueError(
                "Expected RGB/RGBA frame with last dim 3 or 4, "
                f"got {frame.shape[2]} channels"
            )

        normalized = frame[:, :, :3]
        if normalized.dtype != np.uint8:
            normalized = np.clip(normalized, 0, 255).astype(np.uint8)

        if not normalized.flags["C_CONTIGUOUS"]:
            normalized = np.ascontiguousarray(normalized)

        return normalized

    @staticmethod
    def _wrap_text(
        text: str, font: pygame.font.Font, max_width: int, max_lines: int
    ) -> list[str]:
        words = [word for word in text.split(" ") if word]
        if not words:
            return []

        lines: list[str] = []
        current_words: list[str] = []

        for word in words:
            candidate_words = [*current_words, word]
            candidate_text = " ".join(candidate_words)

            if not current_words or font.size(candidate_text)[0] <= max_width:
                current_words = candidate_words
                continue

            lines.append(" ".join(current_words))
            current_words = [word]

            if len(lines) >= max_lines:
                return lines

        if current_words and len(lines) < max_lines:
            lines.append(" ".join(current_words))

        return lines


def run_display_smoketest(
    env_id: str,
    seed: int,
    fps: int,
    window_scale: int,
    subtitle: str,
    subtitle_font: str,
    subtitle_size: int,
    hud: bool,
    text_bands: bool = True,
    min_window_width: int = 960,
    subtitle_max_text_width: int = 960,
    env_kwargs: dict[str, Any] | None = None,
    max_steps: int | None = None,
) -> int:
    """Run a random-agent live display loop for visual smoke validation.

    This helper is intentionally simple: it exercises frame rendering, subtitle
    drawing, keyboard handling, and env reset behavior without narration workers.

    Args:
        env_id: Gymnasium environment id.
        seed: Random seed for reset/action-space sampling.
        fps: Target display framerate.
        window_scale: Integer frame upscaling factor.
        subtitle: Static subtitle text rendered during the smoke run.
        subtitle_font: Font family used for subtitle/HUD text.
        subtitle_size: Subtitle font size in pixels.
        hud: Whether to render HUD text.
        text_bands: Whether to reserve text bands around gameplay.
        min_window_width: Minimum window width in pixels.
        subtitle_max_text_width: Maximum subtitle wrapping width in pixels.
        env_kwargs: Optional kwargs forwarded to ``gym.make``.
        max_steps: Optional upper bound on rendered steps.

    Returns:
        Number of frames rendered before exit.

    Raises:
        ValueError: If ``max_steps`` is provided but non-positive.
    """

    if max_steps is not None and max_steps <= 0:
        raise ValueError("max_steps must be a positive integer when provided")

    env = make_env(env_id=env_id, seed=seed, env_kwargs=env_kwargs)
    agent = RandomAgent(env)
    display = Display(
        env_id=env_id,
        fps=fps,
        window_scale=window_scale,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        hud=hud,
        text_bands=text_bands,
        min_window_width=min_window_width,
        subtitle_max_text_width=subtitle_max_text_width,
    )
    display.set_subtitle(subtitle)

    step = 0
    episode_reward = 0.0

    try:
        observation, _ = env.reset(seed=seed)

        while display.is_open:
            action = agent.act(observation)
            observation, reward, terminated, truncated, _ = env.step(action)
            episode_reward += float(reward)
            frame = env.render()

            if not isinstance(frame, np.ndarray):
                raise TypeError(
                    "Expected render_mode='rgb_array' to return numpy.ndarray, "
                    f"got {type(frame)!r}"
                )

            step += 1
            display.set_status(step=step, episode_reward=episode_reward)
            if not display.blit_frame(frame):
                break

            if max_steps is not None and step >= max_steps:
                break

            if terminated or truncated:
                observation, _ = env.reset()
                episode_reward = 0.0
    finally:
        display.close()
        env.close()

    return step
