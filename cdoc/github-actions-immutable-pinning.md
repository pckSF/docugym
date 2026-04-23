---
type: decision
tags: [security, ci, github-actions, supply-chain]
created: 2026-04-22
updated: 2026-04-23
status: active
related: [security-audit-and-risk-register.md, github-actions-hardening-measures-review.md]
---

# GitHub Actions Immutable Pinning

## Context

A supply-chain incident review was requested after the March 2026 LiteLLM
incident and related CI/CD compromise discussion. The repository used major-tag
references for GitHub Actions in `.github/workflows/ci.yml`, which are mutable.

A prior cdoc finding already identified this as a medium-priority risk in
`security-audit-and-risk-register.md`. This decision resolves that tracked item
for CI workflows and defines ongoing requirements.

## Research

- Repository state before this decision:
  - `actions/checkout@v4`
  - `actions/setup-python@v5`
  - `astral-sh/setup-uv@v4`
- GitHub Secure Use guidance states full-length commit SHA pinning is currently
  the only immutable way to reference third-party actions.
- GitHub notes that inline comments on the same `uses:` line are compatible with
  Dependabot version documentation updates for SHA-pinned actions.
- The runner discussion in `actions/runner#1155` confirms the practical pattern:
  `uses: owner/repo@<sha> # <version-tag>`.
- The LiteLLM March 2026 incident reinforces supply-chain hardening patterns:
  immutable references, stronger release controls, and explicit verification.

### Requirements Evaluated

- Pin all external actions to full 40-character commit SHAs.
- Keep human-readable version context on the same line as `uses:` comments.
- Verify each SHA resolves to the expected upstream action repository tag.
- Maintain an update mechanism (Dependabot and/or scheduled manual rotation) so
  pins do not become stale.
- Prefer repository/organization policy that requires full-length SHA pinning.

### Assumptions

- `confident`: The repository uses GitHub-hosted runners and third-party action
  code executes with meaningful repository access.
- `confident`: Tag-only references (`@vX`) are mutable and are weaker than full
  SHA references for integrity.
- `likely`: Same-line version comments improve maintainability and review speed.
- `uncertain`: Org-level enforcement settings are available and enabled for this
  repository owner.

## Options Considered

#### Option 1: Keep major-tag references only
- **Description:** Continue using `@v4`/`@v5` style references.
- **Pros:** Lowest maintenance; simplest to read.
- **Cons:** Mutable references; weaker protection against upstream compromise or
  tag retargeting.

#### Option 2: Pin only full SHAs without version comments
- **Description:** Use immutable SHAs but omit human-readable version hints.
- **Pros:** Strong immutability and minimal syntax.
- **Cons:** Harder review ergonomics; slower upgrades and audit clarity.

#### Option 3: Pin full SHAs and keep same-line version comments
- **Description:** Use immutable SHAs with comments such as `# v4.3.1`.
- **Pros:** Strong immutability plus readability and better Dependabot metadata
  behavior.
- **Cons:** Comments can become stale if not updated with pin rotations.

## Decision

Option 3 is chosen.

It preserves the immutability advantage of Option 2 while avoiding the audit and
maintainability downsides of opaque SHA-only lines. It also avoids the mutable
reference risk in Option 1. The CI workflow now uses full commit SHAs with
same-line version comments:

- `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1`
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0`
- `astral-sh/setup-uv@e4db8464a088ece1b920f60402e813ea4de65b8f # v4`

## Pre-Mortem

- Pins become stale and miss security updates.
  - Mitigation: enforce periodic review or Dependabot action updates.
- A SHA is copied from an unexpected fork or wrong repository.
  - Mitigation: verify SHA provenance against upstream tags before merge.
- Comment/version drift causes reviewer confusion.
  - Mitigation: require comment refresh in the same PR when updating SHA.
- Policy is documented but not enforced at repo/org settings level.
  - Mitigation: enable GitHub setting to require full-length SHA pins where
    available.

## Changelog

- 2026-04-22: Created decision note and applied SHA pinning with version
  comments in CI workflow.
- 2026-04-23: Linked follow-on hardening review decision note.
