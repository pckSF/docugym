"""Configuration loading tests for YAML parsing and env-var overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from docugym.config import load_settings
from docugym.config_files import ConfigNotFoundError, resolved_config_path

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


def test_load_settings_default_works_outside_repo_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.run.env_id == "ALE/SpaceInvaders-v5"
    assert settings.run.env_kwargs["frameskip"] == 4


def test_resolved_config_path_accepts_known_preset_outside_repo_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    with resolved_config_path("atari") as config_path:
        assert config_path.name == "atari.yaml"
        assert config_path.exists()


def test_resolved_config_path_accepts_configs_relative_preset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    with resolved_config_path("configs/lunarlander.yaml") as config_path:
        assert config_path.name == "lunarlander.yaml"
        assert config_path.exists()


def test_resolved_config_path_rejects_unknown_reference(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(ConfigNotFoundError, match="existing YAML file"):
        with resolved_config_path(missing_path):
            pass


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
