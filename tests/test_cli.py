"""CLI command tests for config merging, overrides, and user-facing validation."""

from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

from typer.testing import CliRunner

from docugym.cli import app


def test_smoketest_command_invokes_runner(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "CartPole-v1"
  env_kwargs:
    frameskip: 2
  seed: 17
agent: {
kind: "sb3",
sb3_repo_id: "sb3/ppo-LunarLander-v2",
sb3_filename: "ppo-LunarLander-v2.zip",
sb3_revision: "0961e4e83c29ec7dd52be7dd08f7c045cb23bda3"
}
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_smoketest(**kwargs: object) -> list[Path]:
        captured.update(kwargs)
        out_dir = Path(str(kwargs["out_dir"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "frame-00000.png"
        output.write_bytes(b"png")
        return [output]

    monkeypatch.setattr("docugym.cli.run_smoketest", fake_run_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "smoketest",
            "--steps",
            "3",
            "--env-kwargs",
            '{"repeat_action_probability": 0.1}',
            "--out-dir",
            str(tmp_path / "frames"),
        ],
    )

    assert result.exit_code == 0
    assert captured["env_id"] == "CartPole-v1"
    assert captured["seed"] == 17
    assert captured["steps"] == 3
    assert captured["agent_kind"] == "random"
    assert captured["sb3_repo_id"] == "sb3/ppo-LunarLander-v2"
    assert captured["sb3_filename"] == "ppo-LunarLander-v2.zip"
    assert captured["sb3_revision"] == "0961e4e83c29ec7dd52be7dd08f7c045cb23bda3"
    assert captured["env_kwargs"] == {
        "frameskip": 2,
        "repeat_action_probability": 0.1,
    }


def test_smoketest_rejects_invalid_env_kwargs(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text('run:\n  env_id: "CartPole-v1"\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "smoketest",
            "--env-kwargs",
            "not-json",
        ],
    )

    assert result.exit_code != 0
    plain_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "env-kwargs" in plain_output
    assert "valid JSON" in plain_output


def test_smoketest_env_override_drops_default_env_kwargs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/SpaceInvaders-v5"
  env_kwargs:
    frameskip: 4
agent:
  sb3_repo_id: "sb3/ppo-LunarLander-v2"
  sb3_filename: "ppo-LunarLander-v2.zip"
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_smoketest(**kwargs: object) -> list[Path]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr("docugym.cli.run_smoketest", fake_run_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--config", str(config_path), "smoketest", "--env", "CartPole-v1"],
    )

    assert result.exit_code == 0
    assert captured["env_kwargs"] == {}


def test_display_smoketest_command_invokes_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
    env_id: "ALE/Breakout-v5"
    env_kwargs:
        frameskip: 4
    seed: 101
    fps: 60
display:
    window_scale: 3
    min_window_width: 960
    subtitle_font: "DejaVu Sans"
    subtitle_size: 22
    subtitle_max_text_width: 960
    hud: true
    text_bands: true
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_display_smoketest(**kwargs: object) -> int:
        captured.update(kwargs)
        return 77

    monkeypatch.setattr("docugym.cli.run_display_smoketest", fake_run_display_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "display-smoketest",
            "--steps",
            "10",
            "--subtitle",
            "Hardcoded subtitle",
            "--env-kwargs",
            '{"repeat_action_probability": 0.1}',
        ],
    )

    assert result.exit_code == 0
    assert captured["env_id"] == "ALE/Breakout-v5"
    assert captured["seed"] == 101
    assert captured["fps"] == 60
    assert captured["window_scale"] == 3
    assert captured["min_window_width"] == 960
    assert captured["subtitle"] == "Hardcoded subtitle"
    assert captured["subtitle_font"] == "DejaVu Sans"
    assert captured["subtitle_size"] == 22
    assert captured["subtitle_max_text_width"] == 960
    assert captured["hud"] is True
    assert captured["text_bands"] is True
    assert captured["max_steps"] == 10
    assert captured["env_kwargs"] == {
        "frameskip": 4,
        "repeat_action_probability": 0.1,
    }


def test_display_smoketest_overlay_flag_overrides_text_bands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Breakout-v5"
display:
  text_bands: true
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_display_smoketest(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("docugym.cli.run_display_smoketest", fake_run_display_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "display-smoketest",
            "--overlay-text",
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["text_bands"] is False


def test_display_smoketest_width_flags_override_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Breakout-v5"
display:
  min_window_width: 960
  subtitle_max_text_width: 960
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_display_smoketest(**kwargs: object) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr("docugym.cli.run_display_smoketest", fake_run_display_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "display-smoketest",
            "--min-window-width",
            "840",
            "--subtitle-max-text-width",
            "700",
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["min_window_width"] == 840
    assert captured["subtitle_max_text_width"] == 700


def test_display_smoketest_env_override_drops_default_env_kwargs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Breakout-v5"
  env_kwargs:
    frameskip: 4
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_display_smoketest(**kwargs: object) -> int:
        captured.update(kwargs)
        return 3

    monkeypatch.setattr("docugym.cli.run_display_smoketest", fake_run_display_smoketest)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "display-smoketest",
            "--env",
            "CartPole-v1",
            "--steps",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert captured["env_kwargs"] == {}


def test_run_command_invokes_runtime_runner(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Pong-v5"
  env_kwargs:
    frameskip: 4
  seed: 21
  fps: 60
agent: {
kind: "random",
sb3_repo_id: "sb3/ppo-SpaceInvadersNoFrameskip-v4",
sb3_filename: "ppo-SpaceInvadersNoFrameskip-v4.zip",
sb3_revision: "c0741d2e949614ef905e2489241c3032d1c9cce3"
}
vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"
display:
  window_scale: 3
  min_window_width: 960
  subtitle_font: "DejaVu Sans"
  subtitle_size: 22
  subtitle_max_text_width: 960
  hud: true
  text_bands: true
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **kwargs: object) -> None:
            captured["narrator_init"] = kwargs

        def wait_until_ready_sync(self, **kwargs: object) -> bool:
            captured["wait_kwargs"] = kwargs
            return True

    class FakeResult:
        rendered_steps = 10
        narration_count = 2
        latency_p50_ms = 850.0
        latency_p95_ms = 1200.0
        dropped_narration_candidates = 1

    def fake_run_session_sync(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr(
        "docugym.cli.run_session_sync",
        fake_run_session_sync,
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "run",
            "--steps",
            "10",
            "--narrate-every",
            "5",
            "--wait-for-vlm",
            "--wait-timeout",
            "3",
            "--env-kwargs",
            '{"repeat_action_probability": 0.1}',
        ],
    )

    assert result.exit_code == 0
    assert captured["env_id"] == "ALE/Pong-v5"
    assert captured["seed"] == 21
    assert captured["fps"] == 60
    interval_seconds = captured["narration_interval_seconds"]
    assert isinstance(interval_seconds, float)
    assert abs(interval_seconds - (5.0 / 60.0)) < 1e-9
    assert captured["agent_kind"] == "random"
    assert captured["sb3_revision"] == "c0741d2e949614ef905e2489241c3032d1c9cce3"
    assert captured["env_kwargs"] == {
        "frameskip": 4,
        "repeat_action_probability": 0.1,
    }
    assert captured["wait_kwargs"] == {"timeout_seconds": 3.0}
    assert captured["record_out_path"] is None


def test_run_policy_shorthand_implies_sb3(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Pong-v5"
agent:
  kind: "random"
vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class FakeResult:
        rendered_steps = 1
        narration_count = 0
        latency_p50_ms = None
        latency_p95_ms = None
        dropped_narration_candidates = 0

    def fake_run_session_sync(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr(
        "docugym.cli.run_session_sync",
        fake_run_session_sync,
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "run",
            "--policy",
            "sb3/ppo-PongNoFrameskip-v4",
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["agent_kind"] == "sb3"
    assert captured["sb3_repo_id"] == "sb3/ppo-PongNoFrameskip-v4"
    assert captured["sb3_filename"] == "ppo-PongNoFrameskip-v4.zip"
    assert captured["sb3_revision"] is None


def test_run_no_voice_flag_enables_subtitle_only_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
    env_id: "ALE/Pong-v5"
agent:
    kind: "random"
vlm:
    base_url: "http://localhost:8000/v1"
    model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
    max_tokens: 80
    temperature: 0.8
    top_p: 0.9
    image_detail: "low"
tts:
    enabled: true
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class FakeResult:
        rendered_steps = 1
        narration_count = 0
        latency_p50_ms = None
        latency_p95_ms = None
        dropped_narration_candidates = 0

    def fake_run_session_sync(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr(
        "docugym.cli.run_session_sync",
        fake_run_session_sync,
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "run",
            "--no-voice",
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["voice_enabled"] is False


def test_run_record_flag_overrides_config(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Pong-v5"
agent:
  kind: "random"
vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"
recording:
  enabled: true
  out_path: "out/from-config.mp4"
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class FakeResult:
        rendered_steps = 1
        narration_count = 0
        latency_p50_ms = None
        latency_p95_ms = None
        dropped_narration_candidates = 0

    def fake_run_session_sync(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr(
        "docugym.cli.run_session_sync",
        fake_run_session_sync,
    )

    out_path = tmp_path / "manual-record.mp4"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "run",
            "--record",
            str(out_path),
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["record_out_path"] == out_path


def test_run_uses_config_recording_path_when_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "ALE/Pong-v5"
agent:
  kind: "random"
vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"
recording:
  enabled: true
  out_path: "out/from-config.mp4"
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class FakeResult:
        rendered_steps = 1
        narration_count = 0
        latency_p50_ms = None
        latency_p95_ms = None
        dropped_narration_candidates = 0

    def fake_run_session_sync(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr(
        "docugym.cli.run_session_sync",
        fake_run_session_sync,
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "run",
            "--steps",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["record_out_path"] == Path("out/from-config.mp4")


def test_list_voices_prints_all_kokoro_voices(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text('run:\n  env_id: "CartPole-v1"\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(config_path), "list-voices"])

    assert result.exit_code == 0
    for voice_id in (
        "bm_george",
        "bm_fable",
        "bm_lewis",
        "bm_daniel",
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
    ):
        assert voice_id in result.output


def test_list_envs_prints_presets(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text('run:\n  env_id: "CartPole-v1"\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(config_path), "list-envs"])

    assert result.exit_code == 0
    assert "atari" in result.output
    assert "lunarlander" in result.output
    assert "carracing" in result.output


def test_tune_prompt_command_invokes_tuning_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  env_id: "CartPole-v1"
  env_kwargs:
    frameskip: 2
  seed: 17
agent: {
kind: "random",
sb3_repo_id: "sb3/ppo-LunarLander-v2",
sb3_filename: "ppo-LunarLander-v2.zip",
sb3_revision: "0961e4e83c29ec7dd52be7dd08f7c045cb23bda3"
}
vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"
""",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeNarrator:
        def __init__(self, **kwargs: object) -> None:
            captured["narrator_init"] = kwargs

        def wait_until_ready_sync(self, **kwargs: object) -> bool:
            captured["wait_kwargs"] = kwargs
            return True

    def fake_run_prompt_tuning(**kwargs: object) -> list[SimpleNamespace]:
        captured.update(kwargs)
        sample_count = kwargs["samples"]
        if not isinstance(sample_count, int):
            raise AssertionError("samples must be an int")
        return [
            SimpleNamespace(
                step=5,
                reward=1.0,
                narration="The patient traveller drifts onward.",
                latency_ms=150.0,
            )
            for _ in range(sample_count)
        ]

    monkeypatch.setattr("docugym.cli.VLMNarrator", FakeNarrator)
    monkeypatch.setattr("docugym.cli.run_prompt_tuning", fake_run_prompt_tuning)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "tune",
            "prompt",
            "--env",
            "CartPole-v1",
            "--samples",
            "3",
            "--step-stride",
            "2",
            "--wait-for-vlm",
            "--wait-timeout",
            "4",
            "--env-kwargs",
            '{"repeat_action_probability": 0.1}',
        ],
    )

    assert result.exit_code == 0
    assert captured["env_id"] == "CartPole-v1"
    assert captured["samples"] == 3
    assert captured["step_stride"] == 2
    assert captured["agent_kind"] == "random"
    assert captured["seed"] == 17
    assert captured["sb3_revision"] == "0961e4e83c29ec7dd52be7dd08f7c045cb23bda3"
    assert captured["wait_kwargs"] == {"timeout_seconds": 4.0}
    assert captured["env_kwargs"] == {
        "frameskip": 2,
        "repeat_action_probability": 0.1,
    }
    assert "[01]" in result.output
    assert "Mean narration latency" in result.output
