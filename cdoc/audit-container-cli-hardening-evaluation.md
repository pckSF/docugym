---
type: decision
tags: [security, docker, supply-chain, chainguard, capabilities, audit]
created: 2026-04-26
updated: 2026-04-26
status: active
related: [security-audit-and-risk-register.md, hashed-requirements-export-from-uv-lock.md, devcontainer-security-settings-review.md]
---

# Audit Container CLI-Free Hardening Evaluation

## Context

The `audit` Docker build stage runs `pip-audit` inside a supply-chain scanning
container whose explicit purpose is to execute dependency-scanning code that
may itself carry supply-chain risk (pip-audit and its transitive deps are
themselves PyPI packages). A prompt was raised: does removing CLI tooling from
this container prevent "string pivots" (a compromised package using shell
commands to exfiltrate data or escalate), and if so is that hardening overkill?

The container at the time of evaluation used:
- Base image: `cgr.dev/chainguard/python` pinned by SHA-256 digest (minimal
  variant — no shell, no package manager, no CLI utilities beyond Python).
- Docker-compose controls: `read_only: true`, `tmpfs: /tmp`,
  `security_opt: no-new-privileges:true`, read-only bind mount (`.:/app:ro`).
- ENTRYPOINT: exec form (`["python", "-m", "pip_audit"]`) — no shell invocation.

## Research

### What Chainguard `python:latest` already provides

Chainguard publishes two variants of their Python image:
- `:latest-dev` — includes `bash`, `ash`, `sh`, `pip`, `apk`, and `uv`.
- `:latest` (minimal) — **no shell, no package manager, no curl/wget/nc** —
  only the Python runtime and its minimal OS dependencies.

The Dockerfile uses the SHA-digest-pinned minimal variant. This means:
- `subprocess.Popen(["sh", "-c", "..."])` → fails; no shell binary present.
- `subprocess.Popen(["curl", ...])` / `["wget", ...]` → fails; not present.
- `os.system("...")` → fails; no shell.

The "string pivot" concern — a compromised package using shell commands to run
arbitrary code or exfiltrate data — is **already addressed** by the base image
choice. This is not accidental: it is the explicit security intent of the
Chainguard minimal variant.

### Residual attack surface after base image

Even in a distroless container, a malicious Python package can still:
1. Make outgoing network connections using Python's `socket`/`urllib` (no shell
   needed).
2. Execute Python itself (`subprocess.Popen(["python", ...])`).
3. Use capability-gated Linux syscalls if capabilities are present (e.g., raw
   sockets via `CAP_NET_RAW`, `CHOWN` via `CAP_CHOWN`, etc.).

Controls (1) and (2) are inherent to having a Python runtime at all; removing
them would remove pip-audit itself. Control (3) is addressable via
`cap_drop: ALL` in the compose service.

### Gap: capabilities not dropped in compose service

The `audit` compose service has no `cap_drop` directive. Linux process
capabilities (e.g., `CAP_NET_RAW`, `CAP_CHOWN`, `CAP_DAC_OVERRIDE`) are
available to the `nonroot` process unless explicitly dropped. Because the
process is nonroot, many caps are inert by default — but not all; bounding
sets still apply, and exploits targeting capability-related paths remain
possible in principle.

`pip-audit`'s operational requirements are: file reads (from the mounted
`/app`), outgoing HTTPS to `api.osv.dev`, and writes to `/tmp`. None of these
require Linux capabilities for an unprivileged process. Dropping all
capabilities is therefore safe.

### Network isolation viability

Running the audit service with `network_mode: none` would block Python-level
socket calls, closing the exfiltration path entirely. However, pip-audit's OSV
vulnerability lookup (`--vulnerability-service osv`, the default) requires
HTTPS access to `api.osv.dev`. Removing network access neutralises the tool's
primary function. Offline database approaches (pre-fetching OSV data) add
significant operational complexity. Network isolation is not a viable option
without fundamentally changing how vulnerability data is consumed.

### Assumptions

- `confident`: Chainguard `python:latest` minimal has no shell or CLI binaries.
- `confident`: pip-audit's OSV queries use standard outgoing TCP — no Linux
  capability required for an unprivileged process making outgoing connections.
- `confident`: `cap_drop: ALL` is safe for a read-files + HTTPS-out workload.
- `confident`: ENTRYPOINT exec form already avoids shell invocation at the
  container entrypoint layer.
- `likely`: The SHA-pinned digest resolves to the minimal (`:latest`) variant
  based on Chainguard documentation that `:latest` always maps to minimal.
- `uncertain`: Whether a future pip-audit version or dependency would introduce
  an operation requiring a capability (e.g., socket raw mode for network
  probing); mitigated by the audit tool's well-defined scope.

## Options Considered

#### Option 1: Accept current posture, no additional changes
- **Description:** Keep the Chainguard distroless base with existing compose
  controls (`read_only`, `tmpfs`, `no-new-privileges`). Take no further action.
- **Pros:** No risk of breaking the audit workflow; no maintenance burden.
- **Cons:** Linux capabilities remain available to the process. A compromised
  pip-audit dependency using `CAP_NET_RAW` (raw sockets), `CAP_CHOWN`, or
  similar capability-gated paths has no kernel-level barrier. The principle of
  least privilege is not fully satisfied.

#### Option 2: Add `cap_drop: ALL` to docker-compose audit service
- **Description:** Add `cap_drop: ["ALL"]` to the `audit` service in
  `docker-compose.yaml`. No Dockerfile changes; the base image already handles
  the CLI-removal concern.
- **Pros:** Eliminates capability-based exploit paths at the kernel level with
  near-zero effort. Closes the last privilege-related gap identified. Aligns
  with OWASP and CIS Docker Benchmark recommendations for least-privilege
  container operation. No functional impact on pip-audit's file-read + HTTPS
  workflow.
- **Cons:** Process already runs as nonroot so most capabilities are unused;
  marginal uplift. Slight risk of breaking a future pip-audit operation that
  requires an unexpected capability (low probability, immediately detectable as
  a permission error).

#### Option 3: Add `network_mode: none` (full network isolation)
- **Description:** Prevent all network access by running the audit container
  with no network interface.
- **Pros:** Closes Python-level socket exfiltration path entirely.
- **Cons:** Breaks pip-audit's OSV vulnerability database queries, making the
  tool non-functional in its default and most useful mode. Preloading an
  offline vulnerability snapshot is operationally costly and introduces a
  freshness risk. This option trades security tool effectiveness for isolation.
  Ruled out.

## Decision

**Option 2.** The Chainguard distroless base already addresses the "string
pivot" / "no CLI" concern — that protection is already live and was a correct
choice. The hardening is therefore **not overkill**: distroless was the right
base, `cap_drop: ALL` is the remaining gap, and closing it costs nothing
functionally.

Option 1 is rejected because it leaves capabilities open without justification.
Option 3 is rejected because it defeats the tool's primary purpose.

Implementation: add `cap_drop: ["ALL"]` to the `audit` service in
`docker-compose.yaml`. No Dockerfile changes required.

## Pre-Mortem

- **pip-audit fails at startup due to capability denial:** Very unlikely.
  pip-audit reads files and makes HTTPS calls; neither needs capabilities.
  Would surface immediately as an error on first run. Fix: add back only the
  specific capability identified.
- **OSV API calls fail:** Outgoing TCP from an unprivileged process does not
  require capabilities; `cap_drop: ALL` does not affect this path. Would
  surface as a connection error, not a permission error, and would indicate a
  network misconfiguration rather than a capability issue.
- **Future pip-audit version requires a capability:** Would surface as a clear
  runtime permission error on upgrade. Mitigation: CI runs the audit container
  on each relevant push; regressions are caught promptly.
- **Chainguard upgrades inadvertently include a shell binary:** The SHA digest
  pin in the Dockerfile prevents this. The digest must be deliberately updated.

## Changelog

- 2026-04-26: Created — evaluated CLI-free hardening request; confirmed
  Chainguard distroless base already resolves string-pivot concern; identified
  `cap_drop: ALL` as the remaining gap; decided to implement.
