from __future__ import annotations

from pathlib import Path

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
agent:
  kind: "sb3"
  sb3_repo_id: "sb3/ppo-LunarLander-v2"
  sb3_filename: "ppo-LunarLander-v2.zip"
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
    assert "--env-kwargs must be valid JSON" in result.output


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
