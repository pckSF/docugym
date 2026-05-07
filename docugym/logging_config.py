"""Project-wide logging configuration helpers.

Keeping logging setup in one module ensures CLI commands and tests emit the same
timestamped format, which simplifies troubleshooting across runtime paths.
"""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure process-wide logging with a stable human-readable format.

    Args:
        level: Logging level name (for example ``INFO`` or ``DEBUG``).
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
