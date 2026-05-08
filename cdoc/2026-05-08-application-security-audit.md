---
type: log
tags: [security, audit, owasp, supply-chain, deserialization, sb3, ci]
created: 2026-05-08
updated: 2026-05-08
status: active
related: [security-audit-and-risk-register.md, 2026-05-07-application-security-audit.md, hashed-requirements-export-from-uv-lock.md, networking-ports-and-services.md, devcontainer-security-settings-review.md, ci-scheduled-pip-audit-job.md, sb3-untrusted-repo-cli-confirmation.md, readonly-compose-profile-for-runp.md, security-audit-remediation-hub.md]
---
# Security Audit Verification & Delta (2026-05-08)

## Context

Follow-up application security audit run after the 2026-05-07 remediation
batch was merged. The baseline full report is recorded in
[2026-05-07-application-security-audit.md](2026-05-07-application-security-audit.md);
this log captures the verification
result, net-new findings, and the derived task list. Date is 2026-05-08.

## Content

### Scope and threat model

Identical to [2026-05-07-application-security-audit.md](2026-05-07-application-security-audit.md): supply-chain attacker
controlling a Python package, Hugging Face repo, or GitHub Action consumed
by this project; low-privilege local user; LAN attacker only when the VLM
sidecar is intentionally re-bound. Source is not secret. No inbound HTTP
server is hosted by the package itself.

### Verification of 2026-05-07 remediations

All five claimed remediations are present in code today:

- SB3 `enforce_trusted_repo` defaults to `True` in both `docugym/config.py`
  and `configs/default.yaml`; fail-closed branch raises `ValueError` for
  non-allowlisted repos.
- `_download_policy` calls `huggingface_hub.hf_hub_download(...,
  revision=revision)` and shipped presets pin `sb3_revision` to a commit SHA.
- `pyproject.toml` declares `voice` and `vlm` optional groups; `kokoro`,
  `sounddevice`, `soundfile`, and `vllm` are present in `requirements.txt`
  with `--hash=sha256:` lines.
- `docker-compose.yaml` sets `security_opt: [no-new-privileges:true]` and
  `cap_drop: [ALL]` on both `dev` and `runp`; the writable `.:/app` mount is
  retained as the documented residual.
- `scripts/serve_vlm.sh` rejects non-loopback `DOCUGYM_VLM_HOST` unless
  `DOCUGYM_VLM_ALLOW_PUBLIC=1`.

### Findings recorded today

- 0 Critical, 0 High.
- 2 Medium: (1) operator opt-out path back into permissive SB3 loading
  remains available via `enforce_trusted_repo: false` and unpinned custom
  repo ids; (2) writable `.:/app` bind mount on `dev`/`runp` is retained
  by design even with the new privilege barriers.
- 1 Low: CI runs only `ruff` and `pytest`; `pip-audit` is opt-in via the
  `audit` Compose service, so newly disclosed CVEs against the hash-pinned
  `requirements.txt` are not surfaced automatically.
- 3 Informational: ffmpeg argv lacks an `--` end-of-options sentinel before
  output paths; the "narration text is data, not code" invariant is
  load-bearing but not documented; subprocess/YAML/JSON/dyn-import/HTTP
  hygiene re-confirmed clean.

The two Medium items are continuations of items already tracked in
[security-audit-and-risk-register.md](security-audit-and-risk-register.md). The Low item is net-new and is the
single most important action to take this week.

### Derived task list

These follow-ups are split into open_task cdocs:

- [sb3-untrusted-repo-cli-confirmation.md](sb3-untrusted-repo-cli-confirmation.md) — require an interactive
  confirmation (or an explicit `--allow-untrusted-repo` flag) at the CLI
  whenever `enforce_trusted_repo` is false or the resolved repo id is
  outside the trusted prefix list, and refuse a custom repo id without a
  revision pin.
- [readonly-compose-profile-for-runp.md](readonly-compose-profile-for-runp.md) — add a `compose --profile
  readonly` overlay (or `runp-ro` service) that mounts `.:/app:ro` and sets
  `read_only: true` for non-edit run workflows; keep the writable mount on
  `dev` for active editing.
- [ci-scheduled-pip-audit-job.md](ci-scheduled-pip-audit-job.md) — add a scheduled GitHub Actions job
  (cron weekly + PR trigger) that runs `pip-audit -r requirements.txt
  --disable-pip` against the exported lock-derived requirements; pin the
  action and tool to a full SHA.

Follow-up resolution is recorded in
[security-audit-remediation-hub.md](security-audit-remediation-hub.md).

### Verification commands

- Manual code re-read of `docugym/env.py`, `docugym/config.py`,
  `docugym/cli.py`, `docugym/narrator.py`, `docugym/recording.py`,
  `docugym/clips.py`, `docugym/tts.py`, `docugym/audio.py`,
  `docugym/logging_config.py`, `configs/default.yaml`,
  `scripts/serve_vlm.sh`, `docker-compose.yaml`, `pyproject.toml`,
  `requirements.txt`, `.github/workflows/ci.yml`,
  `.github/workflows/zizmor.yml`.
- Sink sweeps for `subprocess`, `pickle`, `torch.load`, `eval`, `exec`,
  `compile`, `__import__`, `yaml.load`, `verify=False`, `os.system`,
  `os.popen`, `shell=True`, `tempfile.mktemp`, `requests.`, `httpx.`.
- Secrets sweep for hardcoded keys/tokens/passwords/private keys across
  `docugym/`, `configs/`, `tests/`, `scripts/`, `.github/`, root configs.

## Changelog

- 2026-05-08: Created. Verified 2026-05-07 remediations in place; recorded
  2 Medium / 1 Low / 3 Informational; opened three derived task cdocs.
- 2026-05-08: Linked completed remediation follow-up hub note.
- 2026-05-08: Replaced stale missing root report link with the in-repo baseline audit log reference.
