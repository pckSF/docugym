"""Project-wide logging configuration helpers.

Keeping logging setup in one module ensures CLI commands and tests emit the same
timestamped format, which simplifies troubleshooting across runtime paths.
"""

from __future__ import annotations

import logging

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def configure_logging(level: str = "INFO") -> None:
    """Configure process-wide logging with a stable human-readable format.

    Args:
        level: Logging level name (case-insensitive). Unknown values fall back
            to ``INFO`` so a bad ``--log-level`` never crashes startup.
    """
    normalized = level.upper()
    if normalized not in _VALID_LEVELS:
        normalized = "INFO"

    logging.basicConfig(
        level=normalized,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    if normalized != level.upper():
        logging.getLogger(__name__).warning(
            "Unknown log level %r; defaulting to INFO.", level
        )
