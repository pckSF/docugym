# Documentation Contract

This project targets library-grade documentation quality for source docstrings
and Markdown guides, similar to large public Python libraries.

## Goals

- Make public APIs understandable without reading implementation details.
- Explain behavioral guarantees, failure modes, and non-obvious constraints.
- Keep docs close to code, with no compiled docs pipeline requirement.

## Scope

- In scope: module docstrings, class docstrings, function/method docstrings,
  README and companion Markdown references.
- In scope: `docugym/` and `tests/`.
- Out of scope: generated RST or Sphinx/MkDocs build artifacts.

## Required Docstring Shape

### Modules

- Required in every Python module in `docugym/` and `tests/`.
- Summarize module purpose and why it exists separately.

### Classes

- Required for all classes.
- Explain responsibility and lifecycle, not a member-by-member dump.
- Add `Attributes:` for non-obvious state contracts.

### Public Functions and Methods

Public means symbols that do not begin with `_`.

- Required sections for public API surface:
  - Short summary sentence.
  - `Args:`
  - `Returns:` for non-`None` values.
  - `Raises:` when explicit error paths exist.
- Add `Example:` or `Examples:` when call patterns are easy to misuse.

### Internal Helpers

- Document helpers whose behavior materially affects runtime correctness,
  including async boundaries, queues, buffering, and policy loading.
- Focus on invariants and side effects over obvious mechanics.

## Writing Rules

- Follow Google-style section headers.
- Keep line length compatible with the 88-character formatter target.
- Prefer behavior contracts and constraints over restating type hints.
- Mention defaults only when they impact behavior.

## README Standard

README should cover, in order:

1. Problem framing and value proposition.
2. Installation and system requirements.
3. Quickstart paths.
4. Architecture snapshot.
5. Configuration and API entrypoints.
6. Troubleshooting and contributor workflow.

## Quality Gates

- Doc quality checks run through `scripts/check_doc_quality.py`.
- Initial enforcement focuses on modules, classes, and public callables.
- Strict enforcement can be enabled incrementally as backlog items are closed.
