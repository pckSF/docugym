#!/usr/bin/env python3
"""Validate local Markdown links in repository documentation.

The checker focuses on filesystem-resolvable links and intentionally ignores
external URLs. It is designed for CI use where a fast fail on broken local
references is more important than full web crawling.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _iter_markdown_files(paths: list[Path]) -> list[Path]:
    """Expand CLI path arguments into Markdown file targets.

    Directory arguments are searched recursively for ``*.md`` files. File
    arguments are accepted as-is.
    """

    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
            continue
        if path.is_file():
            files.append(path)
    return sorted(set(files))


def _is_ignored_target(target: str) -> bool:
    """Return whether a link target should be skipped by local checks."""

    lowered = target.strip().lower()
    return lowered.startswith(("http://", "https://", "mailto:", "tel:"))


def _resolve_link_path(raw_target: str, source_file: Path, repo_root: Path) -> Path | None:
    """Resolve one Markdown link target to a filesystem path.

    Anchor-only links (``#section``) resolve to the source file itself and are
    treated as existing without anchor validation.
    """

    target = unquote(raw_target.strip())
    if not target or _is_ignored_target(target):
        return None

    if target.startswith("#"):
        return source_file

    path_part, _, _anchor = target.partition("#")
    if not path_part:
        return source_file

    if path_part.startswith("/"):
        return repo_root / path_part.lstrip("/")

    return (source_file.parent / path_part).resolve()


def _check_file_links(path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """Check one Markdown file for unresolved local links.

    Returns tuples of ``(line_number, target, reason)`` for each unresolved
    local link target.
    """

    failures: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in MARKDOWN_LINK_RE.finditer(line):
            raw_target = match.group(1).strip()
            if _is_ignored_target(raw_target):
                continue

            resolved = _resolve_link_path(raw_target, path, repo_root)
            if resolved is None:
                continue
            if resolved.exists():
                continue

            failures.append((line_number, raw_target, "target does not exist"))
    return failures


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Markdown link checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("docs"), Path("README.md")],
        help="Files or directories to check for local Markdown links.",
    )
    return parser.parse_args()


def main() -> int:
    """Run local Markdown link checks and print findings."""

    args = _parse_args()
    repo_root = Path.cwd().resolve()
    files = _iter_markdown_files(args.paths)
    if not files:
        print("markdown-links: no markdown files found")
        return 0

    failures = 0
    for file_path in files:
        for line_number, target, reason in _check_file_links(file_path, repo_root):
            failures += 1
            rel_path = file_path.relative_to(repo_root)
            print(f"{rel_path}:{line_number}: broken link '{target}' ({reason})")

    if failures:
        print(f"markdown-links: found {failures} broken local link(s)")
        return 1

    print(f"markdown-links: checked {len(files)} file(s), no broken local links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
