---
type: log
tags: [security, audit, owasp, supply-chain, deserialization, sb3]
created: 2026-05-07
updated: 2026-05-08
status: active
related: [security-audit-and-risk-register.md, hashed-requirements-export-from-uv-lock.md, networking-ports-and-services.md, audit-container-cli-hardening-evaluation.md, devcontainer-security-settings-review.md, stage-5-local-tts-streaming-audio.md, 2026-05-08-application-security-audit.md]
---
# Security Audit: docugym Application & Build Surface (2026-05-07)

> Overall posture is solid for a local-only desktop tool with hardened CI and containers. The most serious live finding is that **SB3 model deserialization runs arbitrary code on policy load, and the trusted-repo allowlist is non-enforcing by default** — a typo-squatted Hugging Face repo id only emits a warning before `pickle`-backed code is executed.

**Scope:** `docugym/` Python package (CLI, runtime, narrator, TTS, audio, recording, env, wrapper, clips, tune, config), `configs/*.yaml`, `scripts/serve_vlm.sh`, `Dockerfile`, `docker-compose.yaml`, `requirements.txt`, `pyproject.toml`, `.github/workflows/`. | **Threat model:** (1) supply-chain attacker controlling a Python package, Hugging Face repo, or GitHub Action consumed by this project; (2) low-privilege local user on the same workstation; (3) network attacker on the local LAN segment when the VLM sidecar is intentionally re-bound. Source code is not secret. The application has **no listening HTTP server of its own** — entry points are CLI args, YAML config, env vars, and frames produced by the local Gym env. | **Assumptions:** the operator runs `docugym` interactively on their own workstation; the vLLM sidecar at `vlm.base_url` is locally trusted; Gym/ALE-rendered frames are non-adversarial. | **OWASP 2025:** A01 N/A (no auth/multi-tenancy) · A02 findings · A03 findings · A04 clean · A05 clean (no SQL/shell/template injection sinks; subprocess uses argv list) · A06 N/A (no business logic / accounts) · A07 N/A · A08 findings · A09 clean · A10 clean.

## Executive Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 |
| Medium | 3 |
| Low | 1 |
| Informational | 2 |

Today an attacker who can publish or take over a Hugging Face SB3 repository whose id matches a value the operator passes via `--policy`, `--repo-id`, or `agent.sb3_repo_id` can ship a poisoned `.zip` whose deserialization executes arbitrary code in the operator's user context. The original audit found that the default config kept `enforce_trusted_repo: false`, so untrusted repo ids only produced a `logger.warning` before `stable_baselines3.PPO.load(...)` ran. The single most important action was to flip `enforce_trusted_repo` to `True` by default and pin Hugging Face downloads to a `revision` commit SHA.

## Remediation Update

### Status by Finding

| # | Title | Status | Notes |
|---|---|---|---|
| 1 | SB3 deserialization with non-enforcing trusted-repo default | Patched with residual opt-out risk | `agent.enforce_trusted_repo` now defaults to `true` in code and config presets. Users can still explicitly opt into permissive mode for local or third-party repos. |
| 2 | Hugging Face downloads not pinned to a commit revision | Patched for shipped presets | SB3 downloads now use `huggingface_hub.hf_hub_download(..., revision=...)`; shipped presets carry commit SHA pins and the cache key includes the revision. Explicit custom repo/policy overrides do not inherit an unrelated preset revision. |
| 3 | Voice/inference runtime dependencies outside hashed lock | Patched for documented flows | Voice and VLM extras are declared in `pyproject.toml`, locked in `uv.lock`, and exported into hash-pinned `requirements.txt` with `--all-extras`. Direct ad-hoc package installs remain a bypass risk. |
| 4 | Writable host bind mount on `dev` and `runp` | Partially mitigated; writable mount retained | `dev` and `runp` now set `no-new-privileges:true` and `cap_drop: ALL`. The writable `.:/app` mount remains because those services are active development/run workflows that need repository writes. A read-only profile remains a follow-up. |
| 5 | VLM sidecar public bind via one env var | Patched | Non-loopback `DOCUGYM_VLM_HOST` now refuses to start unless `DOCUGYM_VLM_ALLOW_PUBLIC=1` is also set, and docs call out the network-control requirement. |

### Options Considered

#### Option 1: Minimal documentation-only acknowledgment
- **Description:** Leave code unchanged and document all audit findings as operator responsibilities.
- **Pros:** No dependency churn and no behavioral changes.
- **Cons:** Leaves the high-risk SB3 deserialization path fail-open by default and keeps optional runtime dependencies outside the locked artifact.

#### Option 2: Patch only fail-closed SB3 loading
- **Description:** Flip trusted-repo enforcement and leave revision pinning, optional extras, container hardening, and VLM bind controls for later.
- **Pros:** Reduces the highest risk quickly.
- **Cons:** Leaves mutable HF artifacts, ad-hoc optional installs, and sidecar exposure paths open.

#### Option 3: Patch feasible issues now and document deliberate residual risk
- **Description:** Fail closed on SB3 repo trust by default, pin shipped HF revisions, lock optional voice/VLM dependencies, add compose privilege barriers, require explicit public VLM bind acknowledgement, and document the remaining writable bind/opt-out risks.
- **Pros:** Addresses the high finding and most medium/low findings without inventing a new container workflow.
- **Cons:** Produces large lock/export churn from the VLM dependency tree and keeps writable dev/runp mounts as a residual risk.

### Decision

Option 3 is chosen.

The remediation closes the default SB3 deserialization exposure, makes shipped model artifacts revision-addressed, brings optional voice/VLM dependencies under the lock and hash export, and prevents accidental public VLM binds. The writable development bind mount is not removed in this patch because `dev` and `runp` are editing/runtime services rather than audit-only services; the partial container hardening reduces privilege expansion while preserving the current workflow.

### Pre-Mortem

- Users may set `enforce_trusted_repo: false` or pass a custom repo without a revision and reintroduce SB3 deserialization risk.
    - Mitigation: keep warning text and docs explicit; default presets fail closed and pin revisions.
- The `--all-extras` export may create large generated diffs when VLM transitive dependencies change.
    - Mitigation: keep the command fixed in CI and cdoc; review generated-file churn as a deliberate security tradeoff.
- A malicious process inside `dev` or `runp` can still modify the bind-mounted source tree.
    - Mitigation: retain this as a medium residual finding and consider a read-only compose profile for non-edit workflows.
- Operators may intentionally expose the VLM sidecar publicly without firewall or proxy controls.
    - Mitigation: require `DOCUGYM_VLM_ALLOW_PUBLIC=1` and document that non-loopback binds need network controls.

### Verification

- `uv run ruff check .` passed.
- `uv run pytest -q` passed: 81 tests, 1 existing pygame/pkg_resources warning.
- `uv export --format requirements.txt --all-extras --group dev --no-emit-project --locked --output-file requirements.txt` completed.
- A fresh temp export differed only in uv's generated output-path header; the dependency body matched `requirements.txt` byte-for-byte.
- `DOCUGYM_VLM_HOST=0.0.0.0 ./scripts/serve_vlm.sh` refused to start with exit code 2 before launching vLLM.

## High Findings

### 1. SB3 policy deserialization runs arbitrary code; trusted-repo enforcement is off by default

- **Location:** [docugym/env.py](../docugym/env.py#L165-L189), [docugym/config.py](../docugym/config.py#L29-L37) | **Severity:** High | **Confidence:** High
- **Exploitability:** Medium | **CWE:** CWE-502 | **OWASP 2025:** A08

`load_sb3_policy` warns but does not block untrusted repo ids when `enforce_trusted_repo` is false, then calls `loader.load(str(model_path), device=device)` which under the hood unzips and `pickle`-loads the policy artifact:

```python
trusted_prefixes = _normalize_repo_prefixes(trusted_repo_prefixes)
if not _is_trusted_repo(repo_id, trusted_prefixes):
    message = (
        "Untrusted SB3 repo id '%s' does not match trusted prefixes %s. "
        "SB3 policy deserialization can execute arbitrary code."
    )
    if enforce_trusted_repo:
        raise ValueError(message % (repo_id, trusted_prefixes))
    logger.warning(message, repo_id, trusted_prefixes)
...
return loader.load(str(model_path), device=device)
```

The shipped default in [configs/default.yaml](../configs/default.yaml#L11-L16) and [docugym/config.py](../docugym/config.py#L29-L37) is `enforce_trusted_repo: false`. The CLI accepts `--repo-id` and `--policy` directly ([docugym/cli.py](../docugym/cli.py#L495-L520)) and the `policy` shorthand sets `effective_repo_id = policy` verbatim, so a typo-squat such as `sb3-models/ppo-...` or `sb3X/...` flows straight through.

**Attack path:** attacker publishes a HF repo with a name resembling a real SB3 reference checkpoint (or compromises a non-allowlisted repo the operator already uses) → operator runs `docugym run --policy attacker/ppo-Pong` (or has it set in their YAML) → `huggingface_sb3.load_from_hub` downloads a malicious `.zip` → `PPO.load` deserializes the embedded `pytorch.pth` / pickle blob → arbitrary code executes as the operator's user, with full access to the home directory, SSH keys, and the writable bind mount into the repo.
**Impact:** full local RCE in user context; persistence via `~/.bashrc`, `~/.ssh/`, or via the writable repo bind mount inside a running dev container.
**Remediation:** change the default to `enforce_trusted_repo: true` in [docugym/config.py](../docugym/config.py#L36) and [configs/default.yaml](../configs/default.yaml#L15), so the allowlist fails closed; require an explicit `--allow-untrusted-repo` flag (or `enforce_trusted_repo: false` override) for the warning-only path; add a CLI `typer.confirm()` prompt before loading any non-allowlisted repo even in opt-out mode. The accompanying `revision`-pin remediation in finding 2 should be applied at the same time.

## Medium Findings

### 2. Hugging Face model downloads are not pinned to a commit revision

- **Location:** [docugym/env.py](../docugym/env.py#L97-L113) | **Severity:** Medium | **Confidence:** High
- **Exploitability:** Low | **CWE:** CWE-494 | **OWASP 2025:** A08

`_download_policy` calls `load_from_hub(repo_id=repo_id, filename=filename)` with no `revision=` argument, so it always resolves to the current `main`/`HEAD` of the repo:

```python
from huggingface_sb3 import load_from_hub
...
downloaded_path = Path(load_from_hub(repo_id=repo_id, filename=filename))
```

Even allowlisted `sb3/...` repos can be compromised at the maintainer-account level; without a pinned commit SHA, the next `docugym run` will silently fetch whatever was uploaded most recently. Once cached the file is reused, but first-run on any new host or after cache eviction re-introduces the trust window.
**Attack path:** attacker compromises an allowlisted SB3 maintainer account → pushes a poisoned `.zip` under the existing filename → next operator run downloads it → deserialization triggers finding 1's RCE. The trusted-repo allowlist is bypassed because the repo id itself is unchanged.
**Impact:** RCE chained through finding 1; integrity break on a dependency the user believed was vetted.
**Remediation:** add a `revision: str | None = None` parameter to `load_sb3_policy` / `_download_policy` and forward it as `load_from_hub(..., revision=revision)`; require the configured `agent.sb3_revision` in `configs/default.yaml` for shipped presets; include the revision in the cache directory key so different revisions do not collide.

### 3. Voice/inference runtime dependencies are unpinned and outside the hashed lockfile

- **Location:** [pyproject.toml](../pyproject.toml#L9-L26), [docugym/tts.py](../docugym/tts.py#L82-L95), [docugym/audio.py](../docugym/audio.py#L60-L70) | **Severity:** Medium | **Confidence:** High
- **Exploitability:** Medium | **CWE:** CWE-1357 | **OWASP 2025:** A03

`docugym/tts.py` does `importlib.import_module("kokoro")` and `docugym/audio.py` does `importlib.import_module("sounddevice")`, but neither `kokoro` nor `sounddevice` (nor `vllm` for the sidecar) appear in `pyproject.toml` `dependencies` or in the hash-pinned `requirements.txt`:

```python
kokoro_module = importlib.import_module("kokoro")
KPipeline = getattr(kokoro_module, "KPipeline")
...
sd = importlib.import_module("sounddevice")
```

Operators following the README (or [specification.md](../specification.md#L138-L148)) are instructed to `uv pip install kokoro soundfile sounddevice` ad-hoc, which bypasses the lockfile and `--require-hashes` audit container. `kokoro` on PyPI is a third-party-published name, easily typo-squatted (`kokoro-tts`, `kokoros`, etc.).
**Attack path:** operator copies the README install command → resolver fetches whichever `kokoro` is currently on PyPI without hash verification → a future-compromised release executes its `setup.py`/`__init__.py` in the venv → import-time code runs as the operator.
**Impact:** install-time and import-time RCE on any host that follows the documented optional-feature install path; the hardened `audit` Compose service does not see these packages.
**Remediation:** add `kokoro`, `sounddevice`, and `soundfile` to `pyproject.toml` as optional groups (e.g. `[project.optional-dependencies] voice = [...]`) with version bounds, regenerate `requirements.txt` via `uv export` so they receive `--hash=` lines, and document `uv sync --extra voice` (or `pip install -r requirements.txt`) instead of unconstrained ad-hoc installs.

### 4. Writable host bind mount on `dev` and `runp` Compose services

- **Location:** [docker-compose.yaml](../docker-compose.yaml#L13-L17), [docker-compose.yaml](../docker-compose.yaml#L31-L35) | **Severity:** Medium | **Confidence:** High
- **Exploitability:** Medium | **CWE:** CWE-732 | **OWASP 2025:** A02

Both `dev` and `runp` mount the repository writable into the container with no `:ro`, no `read_only:` filesystem, no `cap_drop`, and no `security_opt: no-new-privileges`:

```yaml
volumes:
  - .:/app
working_dir: /app
```

Compare to the hardened `audit` service which uses `:ro`, `read_only: true`, `cap_drop: [ALL]`, and `security_opt: [no-new-privileges:true]`. Any code running inside `dev`/`runp` (an installed dependency, a `pre-commit` hook, a malicious model load from finding 1) can rewrite the host repo, drop a backdoor in `.git/hooks/`, or modify `pyproject.toml` to fetch attacker dependencies on the next `uv sync`.
**Attack path:** any of findings 1/2/3 lands code execution inside the container → process writes to `/app/.git/hooks/post-commit` or `/app/docugym/__init__.py` → the next host-side `git commit` or `python -m docugym` runs the implant outside the container boundary.
**Impact:** container-to-host repository tampering and persistence; nullifies the non-root-user mitigation already present in the image.
**Remediation:** for `dev`/`runp`, add `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]` (re-adding only the capabilities needed for `pygame`/`sounddevice` if any), and document a `compose --profile readonly` variant that mounts `.:/app:ro` for non-edit workflows. This finding has been carried in [security-audit-and-risk-register.md](security-audit-and-risk-register.md) as a `confident` medium for several iterations and remains open.

## Low Findings

### 5. VLM sidecar bind interface is overridable to a public address via a single env var

- **Location:** [scripts/serve_vlm.sh](../scripts/serve_vlm.sh#L1-L17) | **Severity:** Low | **Confidence:** High
- **Exploitability:** Low | **CWE:** CWE-668 | **OWASP 2025:** A02

The script defaults to `127.0.0.1` (good), but `DOCUGYM_VLM_HOST=0.0.0.0` flips it without any further confirmation:

```bash
HOST="${DOCUGYM_VLM_HOST:-127.0.0.1}"
exec vllm serve "${MODEL}" ... --host "${HOST}" --port "${PORT}"
```

vLLM has no auth, so any LAN peer that finds the open port gets free GPU inference and can probe model behavior, exfiltrate prompts/images that the local docugym client posts, or pivot for resource abuse.
**Attack path:** operator on a coffee-shop / co-working LAN sets `DOCUGYM_VLM_HOST=0.0.0.0` for remote-debug convenience → unauthenticated peers send chat-completion requests to port 8000 → free model use and visibility into any concurrent docugym narration traffic.
**Impact:** unauthenticated model misuse and possible prompt/image leakage to LAN.
**Remediation:** in `scripts/serve_vlm.sh`, when `DOCUGYM_VLM_HOST` is non-loopback, print a red warning to stderr and require `DOCUGYM_VLM_ALLOW_PUBLIC=1` to proceed; document that any non-loopback bind must sit behind a reverse proxy with auth. Already tracked in [security-audit-and-risk-register.md](security-audit-and-risk-register.md).

## Informational

### 6. `subprocess` usage in recorder is safe — argv list, no shell, binary resolved via `shutil.which`

- **Location:** [docugym/recording.py](../docugym/recording.py#L41-L46), [docugym/recording.py](../docugym/recording.py#L173-L178), [docugym/recording.py](../docugym/recording.py#L211-L243) | **Severity:** Informational | **Confidence:** High

`FFmpegSessionRecorder.__init__` resolves the binary with `shutil.which(ffmpeg_binary)` and refuses to start if it is missing; both the encode (`subprocess.Popen`) and mux (`subprocess.run`) calls pass argv lists with `shell=False` (the default) and no user-controlled string is interpolated into a shell. The only operator-controlled value reaching the argv is `out_path`, which is a `pathlib.Path` from CLI/config and does not parse as flag injection because it is passed as a positional argument after explicit `-i`/`-c` switches. No remediation needed.

### 7. CI, dependency, and YAML-loading hygiene

- **Locations:** [.github/workflows/ci.yml](../.github/workflows/ci.yml#L7-L40), [requirements.txt](../requirements.txt), [docugym/cli.py](../docugym/cli.py#L101-L106) | **Severity:** Informational | **Confidence:** High

`actions/checkout`, `actions/setup-python`, and `astral-sh/setup-uv` are pinned to full commit SHAs with same-line version comments; the workflow declares `permissions: contents: read` and `persist-credentials: false`; `requirements.txt` is exported with `--hash` lines from `uv.lock` and CI fails the build on drift. YAML config files are parsed with `yaml.safe_load`, never `yaml.load`. JSON CLI input (`_parse_env_kwargs`) uses `json.loads` and validates the result is a `dict`. No remediation needed.

## Phase 4 — Secrets sweep

Searched the working tree (source, tests, fixtures, configs, CI) for `api_key`, `API_KEY`, `secret`, `token`, `password`, `private_key`. The only matches are the `max_tokens` integer parameter for the VLM client and `file_secret_settings` (the pydantic-settings file-secrets source plumbing) — no real credentials, no keys, no leaked tokens. **No rotation required.**

## Non-security observations

- Default `vlm.base_url` is `http://localhost:8000/v1` — fine in scope, but if it ever moves cross-host the lack of TLS would matter.
- `narrator.py` re-creates an `httpx.AsyncClient` per call inside `narrate_frame_sync`; not a security issue, just resource churn — already on the open code-review list.

## Summary Table

| # | Title | Severity | Confidence | Exploitability | CWE | OWASP |
|---|---|---|---|---|---|---|
| 1 | SB3 deserialization with non-enforcing trusted-repo default | High | High | Medium | CWE-502 | A08 |
| 2 | Hugging Face downloads not pinned to a commit revision | Medium | High | Low | CWE-494 | A08 |
| 3 | `kokoro`/`sounddevice`/`vllm` unpinned, outside hashed lock | Medium | High | Medium | CWE-1357 | A03 |
| 4 | Writable host bind mount on `dev`/`runp` Compose services | Medium | High | Medium | CWE-732 | A02 |
| 5 | VLM sidecar host override allows public bind without confirmation | Low | High | Low | CWE-668 | A02 |
| 6 | Recorder `subprocess` invocation is safe (no remediation) | Informational | High | n/a | — | A05 |
| 7 | CI/dependency/YAML hygiene clean (no remediation) | Informational | High | n/a | — | A03/A08 |

## Changelog

- 2026-05-07: Created. Application+build security audit covering OWASP 2025 sweep and Phase 4 secrets sweep; cross-references existing rolling register.
- 2026-05-07: Added remediation decision record, status table, residual-risk rationale, and verification results after patching feasible findings.
- 2026-05-08: Normalized repository file links to `../...` paths so all cdoc markdown references resolve correctly from within `cdoc/`.
