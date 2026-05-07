from __future__ import annotations

from typing import TYPE_CHECKING

from docugym.config import load_settings

if TYPE_CHECKING:
    from pathlib import Path


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_yaml(
        config_path,
        """
run:
  env_id: "CartPole-v1"
  fps: 30
""",
    )

    settings = load_settings(config_path)

    assert settings.run.env_id == "CartPole-v1"
    assert settings.run.fps == 30


def test_environment_overrides_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    _write_yaml(
        config_path,
        """
run:
  env_id: "CartPole-v1"
  fps: 30
""",
    )
    monkeypatch.setenv("DOCUGYM_RUN__FPS", "75")

    settings = load_settings(config_path)

    assert settings.run.fps == 75


def test_agent_defaults_enforce_trusted_repo_and_pin_revision(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_yaml(config_path, 'run:\n  env_id: "CartPole-v1"\n')

    settings = load_settings(config_path)

    assert settings.agent.enforce_trusted_repo is True
    assert settings.agent.sb3_revision == "c0741d2e949614ef905e2489241c3032d1c9cce3"
