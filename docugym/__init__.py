"""Public package exports for the DocuGym wrapper-oriented API.

Importing from this module provides a stable, minimal entrypoint for library users
who want Gym-compatible narration integration.
"""

from __future__ import annotations

from docugym.wrapper import DocuWrapper, docuwrapper

__all__ = ["__version__", "DocuWrapper", "docuwrapper"]

__version__ = "0.1.0"
