---
type: decision
tags: [security, devcontainer, docker-compose]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [security-audit-and-risk-register.md, networking-ports-and-services.md]
---

# Devcontainer Security Settings Review

## Context

A security review was requested for the devcontainer settings that previously
used `security_opt: seccomp=unconfined` and `ipc: host` in
`docker-compose.yaml`, with an inline comment claiming they were acceptable for
local development.

## Research

- Docker documentation on seccomp states the default seccomp profile is a
  least-privilege allowlist and is recommended as the sane default; using
  `seccomp=unconfined` disables this protection.
- `ipc: host` shares the host IPC namespace with the container, which weakens
  isolation boundaries and increases impact if untrusted code executes in the
  container.
- Compose supports `shm_size` for increasing `/dev/shm` without requiring host
  IPC namespace sharing.
- This repository does not currently require privileged container syscalls as a
  hard requirement for normal development tasks.

### Assumptions

- `likely`: Stage 3 and current development workflows do not require host IPC
  namespace sharing.
- `likely`: `shm_size: "2gb"` is sufficient for current ML/dev workloads that
  need larger shared memory.
- `uncertain`: future workloads (for example specific vLLM modes) may require
  temporary exceptions on some hosts.

## Options Considered

#### Option 1: Keep `seccomp=unconfined` and `ipc: host`
- **Description:** Preserve current behavior and keep the local-dev exception.
- **Pros:** Maximum compatibility with edge-case tooling.
- **Cons:** Avoidable reduction in container isolation and larger blast radius.

#### Option 2: Remove both settings and use explicit `shm_size`
- **Description:** Use safer defaults and keep required shared-memory capacity.
- **Pros:** Better default isolation while preserving practical ML usability.
- **Cons:** Some edge workflows may need explicit opt-in overrides later.

#### Option 3: Move risky settings behind a separate optional profile
- **Description:** Keep hardened defaults in base compose and define a debug
  override file/profile for exceptional cases.
- **Pros:** Strong security defaults plus explicit escape hatch.
- **Cons:** Additional maintenance complexity not yet needed.

## Decision

Option 2 was chosen. The repository now removes `seccomp=unconfined` and
`ipc: host` from default services and sets `shm_size: "2gb"` for `dev` and
`runp`. This keeps a safer baseline without blocking expected local workflows.
If a future workflow proves incompatible, an explicit opt-in override can be
added later instead of weakening defaults for everyone.

## Pre-Mortem

- A future GPU/VLM flow might require host IPC for performance or compatibility.
  Mitigation: add an explicit optional override profile instead of changing
  secure defaults.
- `2gb` shared memory may be insufficient on some hosts.
  Mitigation: document the setting and allow local override when needed.
- Team members may assume old behavior still exists.
  Mitigation: track this decision in cdoc and rolling security audit.

## Changelog

- 2026-04-20: Created.
