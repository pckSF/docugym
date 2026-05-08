---
type: note
tags: [security, remediation, audit, hub]
created: 2026-05-08
updated: 2026-05-08
status: active
related: [2026-05-08-application-security-audit.md, ci-scheduled-pip-audit-job.md, sb3-untrusted-repo-cli-confirmation.md, readonly-compose-profile-for-runp.md, security-audit-and-risk-register.md]
---
# Security Audit Remediation Hub (2026-05-08)

## Context

This hub tracks the remediation cluster opened by the
[2026-05-08-application-security-audit.md](2026-05-08-application-security-audit.md)
follow-up audit.

## Content

The cluster contains three independent-but-related subtasks that were executed
in dependency order and cross-linked for future audits:

- [sb3-untrusted-repo-cli-confirmation.md](sb3-untrusted-repo-cli-confirmation.md):
  Added CLI opt-in and confirmation gating for untrusted SB3 policy loading,
  plus required revision pins for non-allowlisted repositories.
- [readonly-compose-profile-for-runp.md](readonly-compose-profile-for-runp.md):
  Added a hardened `runp-ro` path (`readonly` profile) to bound writable-bind
  risk to explicit editing/iteration workflows.
- [ci-scheduled-pip-audit-job.md](ci-scheduled-pip-audit-job.md):
  Added automated dependency CVE scanning in GitHub Actions using
  dependency-change triggers and a weekly schedule for disclosure-lag coverage.

## Changelog

- 2026-05-08: Created hub note and linked all remediation subtasks.
