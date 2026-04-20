---
type: reference
tags: [networking, ports, services, infra]
created: 2026-04-20
updated: 2026-04-20
status: active
related: [stage-3-display-layer.md, security-audit-and-risk-register.md]
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
  - Recommendation: bind to localhost only in local development.

### Current outbound connections

- HTTPS `443/tcp` to model/package sources
  - Hugging Face Hub (`huggingface_sb3.load_from_hub`) for SB3 policy downloads.
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
