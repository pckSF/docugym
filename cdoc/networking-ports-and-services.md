---
type: reference
tags: [networking, ports, services, infra]
created: 2026-04-20
updated: 2026-05-07
status: active
related: [stage-3-display-layer.md, security-audit-and-risk-register.md, devcontainer-security-settings-review.md, 2026-05-07-application-security-audit.md]
---

# Networking Ports and Services

## Context

This note tracks active and planned network connections, ports, and service
roles for DocuGym. It is the single place to check what should be listening,
what should be called, and which links are currently only planned.

## Content

### Current active topology

- No host ports are published in `docker-compose.yaml` for `dev` or `runp`.
- No long-running API server is started by default in the current stages.
- In current devcontainer runs, `localhost:8000` is typically not listening
  unless a VLM sidecar is launched manually.
- `scripts/serve_vlm.sh` now binds the sidecar to `127.0.0.1` by default
  (`DOCUGYM_VLM_HOST` override available for explicit broader exposure).
- Non-loopback `DOCUGYM_VLM_HOST` values require
  `DOCUGYM_VLM_ALLOW_PUBLIC=1`; otherwise the helper exits before launching
  vLLM.

### Configured local endpoint (not always running)

- `http://localhost:8000/v1`
  - Role: OpenAI-compatible VLM API base URL.
  - Used by: `vlm.base_url` defaults in `configs/default.yaml` and
    `docugym/config.py`.
  - Service expected to provide it: vLLM sidecar (planned Stage 4 runtime).

### Planned inbound/listening services

- Port `8000/tcp` (localhost-bound)
  - Service: `vllm serve Qwen/Qwen3-VL-8B-Instruct-AWQ` sidecar.
  - Purpose: frame-to-narration inference endpoint.
  - Recommendation: bind to localhost only in local development. Any
    non-loopback bind should be behind firewall, VPN, or authenticated proxy
    controls and must be acknowledged with `DOCUGYM_VLM_ALLOW_PUBLIC=1`.

### Current outbound connections

- HTTPS `443/tcp` to model/package sources
  - Hugging Face Hub (`huggingface_hub.hf_hub_download`) for SB3 policy
    downloads, preferably with configured commit revision pins.
  - Python package indexes (during dependency installation).

### Non-network local interfaces (for clarity)

- PyGame display output is local graphics I/O, not a network socket.
- Sounddevice/PortAudio output is local audio I/O, not a network socket.

### Operating guidance

- Treat `localhost:8000` as a dependency endpoint, not a guarantee that a
  server is running.
- Before narration-stage testing, verify connectivity explicitly:
  - `curl -sS http://localhost:8000/v1/models`

## Changelog

- 2026-04-20: Created.
- 2026-04-20: Linked rolling security audit reference note.
- 2026-04-20: Linked devcontainer security settings decision note.
- 2026-05-07: Updated VLM sidecar binding behavior to localhost-default with
  explicit env override path.
- 2026-05-07: Documented `DOCUGYM_VLM_ALLOW_PUBLIC=1` requirement for
  non-loopback VLM binds and updated SB3 download reference to revision-aware
  Hugging Face Hub usage.
