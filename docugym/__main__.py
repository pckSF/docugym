"""Module execution entrypoint for ``python -m docugym``.

Delegates directly to the Typer application defined in ``docugym.cli``.
"""

from __future__ import annotations

from docugym.cli import app

if __name__ == "__main__":
    app()
