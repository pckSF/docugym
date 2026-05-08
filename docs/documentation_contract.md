# Documentation Contract

This contract defines quality and maintenance expectations for DocuGym
documentation.

## Mission

Documentation should make DocuGym usable without requiring implementation dives.
It should describe expected behavior, boundaries, and operational tradeoffs with
enough precision for both users and contributors.

## Scope

In scope:

- Source docstrings in `docugym/` and `tests/`
- User guides in `docs/`
- Root README documentation

Out of scope:

- Generated documentation artifacts
- Static-site build tooling output

## Documentation Information Architecture

The `docs/` folder is organized into:

- Entry/navigation page (`docs/index.md`)
- Task guides (for example getting started, troubleshooting)
- Concept guides (architecture and integration behavior)
- Reference material (API and configuration)
- Contributor guidance

Every new user-facing feature should update:

1. At least one task or concept page.
2. The relevant reference page.
3. README when discovery or setup behavior changes.

## Source-of-Truth Rules

- Python signatures and behavior contracts are source-of-truth in code.
- `docs/api_reference.md` reflects stable exported API and CLI surface.
- `docs/config_reference.md` reflects settings models and packaged defaults.
- README provides top-level orientation and links to deeper docs.

## Docstring Quality Requirements

## Modules

- Required in each Python module in `docugym/` and `tests/`.
- Must explain module responsibility and role in system architecture.

## Classes

- Required for every class.
- Must describe responsibility and lifecycle.
- Include `Attributes:` where state contracts are non-obvious.

## Public Functions and Methods

Public means symbols that do not begin with `_`.

Required structure:

- Summary sentence
- `Args:`
- `Returns:` when non-`None`
- `Raises:` for explicit failure paths

Add `Example:` or `Examples:` when usage can be misapplied easily.

## Internal Helpers

Document internals that materially affect correctness or operability, especially:

- queue/backpressure behavior
- async boundaries and cancellation behavior
- trust/security checks
- resource lifecycle semantics

## Writing Style

- Use Google-style section headers.
- Prefer behavior and constraints over restating type hints.
- Keep examples minimal but executable in principle.
- Mention defaults where they influence outcomes.
- Keep content concise; link to related docs instead of duplicating prose.

## README Standard

README should cover:

1. What DocuGym is and why to use it.
2. Requirements and installation.
3. Quickstart paths.
4. Architecture summary.
5. CLI and library usage pointers.
6. Troubleshooting and development workflow.
7. Links to reference docs.

## Quality Gates

Documentation quality is enforced with `scripts/check_doc_quality.py`.

Strict run:

```bash
python3 scripts/check_doc_quality.py --strict docugym tests
```

Checker levels:

- `bare`: no docstring
- `minimal`: present but structurally shallow
- `standard`: complete contract-level documentation
- `rich`: complete plus helpful context (examples/notes)

Default thresholds:

- Core modules (`docugym/`): minimum `standard`
- Test modules (`tests/`): minimum `minimal`

Tunable flags:

- `--min-level-core`
- `--min-level-tests`

## Change Management Expectations

- Do not silently change meaning in docs during broad cleanup.
- When behavior changes, update docs in the same change set.
- Prefer additive clarification over deleting context unless obsolete.
- Keep links local and valid; run a quick manual link check after edits.
