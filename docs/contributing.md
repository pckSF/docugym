# Contributing and Quality Gates

This page describes local development setup and mandatory checks.

## Development Environment

Preferred setup with uv:

```bash
uv sync --extra vlm --extra voice
```

Alternative pip-based setup:

```bash
python3 -m pip install -e .
python3 -m pip install -e ".[vlm,voice]"
python3 -m pip install pre-commit pytest ruff
```

## Pre-commit

Install and run pre-commit hooks:

```bash
pre-commit install
pre-commit run --all-files
```

## Local Quality Gates

Run documentation quality checks:

```bash
python3 scripts/check_doc_quality.py --strict docugym tests
python3 scripts/check_markdown_links.py docs README.md
uv tool run --from mkdocs==1.6.1 mkdocs build --strict
```

Run lint and tests:

```bash
uv run ruff check .
uv run pytest -q
```

## Documentation Expectations

- Keep docs source-first in Markdown.
- Update related docs when behavior, defaults, or CLI surfaces change.
- Keep links relative and local within this folder when possible.
- Follow the quality standards in [Documentation Contract](documentation_contract.md).

## Suggested Documentation Update Workflow

1. Update the affected user-facing guide (for example CLI or architecture).
2. Update [API Reference](api_reference.md) if signatures or fields changed.
3. Update [Configuration Reference](config_reference.md) if defaults/schema changed.
4. Run strict doc-quality and tests.
5. Include docs changes in the same PR as behavior changes.

## CI Coverage

The repository CI enforces core checks and includes dependency vulnerability
scanning. Keep local and CI expectations aligned by running the commands above
before opening a pull request.
