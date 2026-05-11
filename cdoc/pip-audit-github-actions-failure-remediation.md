---
type: decision
tags: [security, ci, supply-chain, dependencies, pip-audit, github-actions]
created: 2026-05-11
updated: 2026-05-11
status: active
related: [ci-scheduled-pip-audit-job.md, hashed-requirements-export-from-uv-lock.md]
---
# Pip Audit GitHub Actions Failure Remediation

## Context

GitHub Actions began failing on the `Dependency CVE Audit` workflow step
`Run pip-audit against lock-derived requirements`.

The failure was not a workflow execution bug: `pip-audit` reported active
vulnerabilities in the lock-derived requirements export.

This note now consolidates both phases of the incident: the initial fixable
dependency uplift and the subsequent strict fail-closed policy update.

## Research

- Reproduced the failing workflow command locally:
  `uv tool run --from pip-audit==2.9.0 pip-audit -r requirements.txt --disable-pip`.
- Confirmed advisories were reported for `diskcache`, `pillow`, `pytest`, and
  `transformers` from `requirements.txt`.
- Confirmed lock/export policy constraints from
  `hashed-requirements-export-from-uv-lock.md`: requirements must stay lock-derived
  via `uv export --all-extras --group dev --no-emit-project --locked`.
- Confirmed prior CI audit policy from `ci-scheduled-pip-audit-job.md`: default
  failure on advisories is intentional and part of the security control.
- Verified fixability from advisory output:
  - `pillow` had stable fix versions available (`12.2.0`).
  - `pytest` had stable fix version available (`9.0.3`).
  - `diskcache` advisory listed no fix version.
  - `transformers` advisory fix was `5.0.0rc3` (pre-release major line), not a
    practical immediate uplift for this repository's optional VLM stack.
- Applied dependency constraint updates in `pyproject.toml`, regenerated
  `uv.lock`, and regenerated `requirements.txt`.
- Re-ran `pip-audit` in two modes:
  - temporary narrow-ignore mode after fixable upgrades,
  - strict fail-closed mode with no ignores (final policy).

### Assumptions

- confident: fixable advisories should be resolved by dependency upgrades rather
  than ignored.
- confident: lock/export determinism must be preserved, so changes must flow
  through `uv.lock` and generated `requirements.txt`.
- likely: temporary ignore IDs can be a short-term bridge, but strict
  fail-closed policy provides clearer long-term signaling.
- likely: unresolved advisories in strict mode require either upstream stable
  fixes or deliberate dependency-surface changes.
- uncertain: upstream timelines for a stable `transformers` fix compatible with
  the repository's optional VLM dependency chain.

## Options considered

#### Option 1: Ignore all pip-audit failures in CI (rejected)
- **Description:** Change workflow to warning-only behavior (for example always
  succeed or add a broad suppression).
- **Pros:** Immediate green workflow.
- **Cons:** Removes the vulnerability gate and conflicts with prior security
  decisions.
- **Why ruled out:** Rejected because it weakens a recently added control and
  hides actionable advisories.

#### Option 2: Upgrade fixable dependencies and ignore only non-actionable IDs (temporary)
- **Description:** Raise constraints for patched stable versions, regenerate lock
  artifacts, and keep a minimal explicit ignore list for advisories without
  practical immediate remediation.
- **Pros:** Preserves CI gate semantics for most advisories and removes fixable
  CVEs quickly.
- **Cons:** Leaves suppression debt and can obscure long-lived unresolved risk.

#### Option 3: Strict fail-closed with no ignore IDs (final)
- **Description:** Keep default `pip-audit` failure semantics with no advisory
  suppressions.
- **Pros:** Maximum transparency and strongest gate semantics.
- **Cons:** Workflow remains red until all advisories are truly remediated.

#### Option 4: Remove dev/extra dependencies from audited requirements (rejected)
- **Description:** Narrow audit scope to runtime-only dependencies.
- **Pros:** Fewer advisory hits and less churn.
- **Cons:** Conflicts with existing lock-export decision to include extras/dev
  in the audited artifact and reduces visibility into optional supply-chain
  surface.
- **Why ruled out:** Rejected due direct conflict with existing security and
  export policy.

## Decision

Choose Option 3 as final policy.

The remediation sequence was:

1. Upgrade fixable advisories (`pillow`, `pytest`) and refresh lock/export.
2. Temporarily use narrow ignore IDs for non-actionable advisories.
3. Remove ignore IDs and adopt strict fail-closed policy.

The workflow now fails on any advisory, including unresolved items such as:

- `GHSA-w8v5-vhqr-4h9v` (`diskcache`, no published fix version).
- `GHSA-69w3-r845-3855` (`transformers`, fix currently in `5.0.0rc3`).

## Pre-Mortem

- Failure mode: strict pipeline remains red for extended periods.
  - Mitigation in note: keep unresolved advisories explicit, and prioritize
    upstream tracking or dependency-surface remediation work.
- Failure mode: upgraded dependency versions break runtime/tests.
  - Mitigation in note: rerun lint/test/docs checks and keep lock/export changes
    in the same remediation pass.
- Failure mode: lock/export drift causes CI mismatch.
  - Mitigation in note: regenerate `uv.lock` and `requirements.txt` together and
    validate deterministic export behavior.
- Failure mode: contributors reintroduce ignore flags ad hoc.
  - Mitigation in note: this decision records strict fail-closed policy; any
    future suppression must be a separately documented exception.

## Outcome

- Updated `pyproject.toml` constraints:
  - `pillow>=12.2.0,<13`
  - `pytest>=9.0.3,<10`
- Regenerated `uv.lock` and `requirements.txt` from lock/export workflow.
- Updated `.github/workflows/pip-audit.yml` twice in sequence:
  - temporary narrow-ignore phase,
  - final strict fail-closed phase with ignore IDs removed.
- Adjusted `scripts/check_markdown_links.py` line wrapping to satisfy CI Ruff.

## Verification

- `uv tool run --from pip-audit==2.9.0 pip-audit -r requirements.txt --disable-pip`
  fails with 2 known vulnerabilities (expected under strict policy).
- `uv run ruff check .` passed.
- `uv run pytest -q` passed (95 tests).
- `python3 scripts/check_markdown_links.py docs README.md` passed.
- `uv tool run --from mkdocs==1.6.1 mkdocs build --strict` passed.

## Changelog

- 2026-05-11: Created after reproducing the failing workflow, applying
  dependency and workflow remediations, and re-validating local workflow
  equivalents.
- 2026-05-11: Updated in place to consolidate strict fail-closed follow-up and
  remove split-note legacy for the same incident.
