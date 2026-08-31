from __future__ import annotations

import logging

from docugym.logging_config import configure_logging


def test_configure_logging_accepts_valid_level() -> None:
    configure_logging("debug")

    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_falls_back_on_invalid_level() -> None:
    configure_logging("NOT_A_LEVEL")

    assert logging.getLogger().level == logging.INFO
