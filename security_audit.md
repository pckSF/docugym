# Security Audit: docugym Application & Build Surface (2026-05-08)

> Overall posture is strong. The 2026-05-07 audit's High and Medium remediations
> are present and verified in code today; this re-audit found no new High or
> Critical findings. The most material residual issue is that **`pip-audit` is
> only available via a manually invoked Compose profile** — newly disclosed
> dependency CVEs are not surfaced by scheduled CI, so a vulnerable transitive
> can sit in the hash-pinned export indefinitely without operator action.

**Scope:** `docugym/` Python package (CLI, runtime, narrator, TTS, audio,
recording, env, wrapper, clips, tune, config, prompts, queue/utility modules),
`configs/*.yaml`, `scripts/serve_vlm.sh`, `Dockerfile`, `docker-compose.yaml`,
`requirements.txt`, `pyproject.toml`, `.github/workflows/`, `.github/dependabot.yml`,
`.pre-commit-config.yaml`, `tests/`. | **Threat model (defaults, unchanged from
2026-05-07):** (1) supply-chain attacker controlling a Python package, Hugging
Face repo, or GitHub Action consumed by this project; (2) low-privilege local
user on the same workstation; (3) network attacker on the local LAN segment
when the VLM sidecar is intentionally re-bound. Source code is not secret.
The application has no inbound HTTP server of its own — entry points are CLI
args, YAML config files, environment variables (only `DOCUGYM_VLM_*` for the
sidecar script), and frames produced by the local Gym env. | **Assumptions:**
the operator runs `docugym` interactively on their own workstation; the vLLM
sidecar at `vlm.base_url` is locally trusted; Gym/ALE-rendered frames are not
adversarial; the local VLM is not actively malicious (its outputs may still be
prompt-injection-influenced in multimodal contexts and are treated as untrusted
strings, not code). | **OWASP 2025:** A01 N/A (no auth/multi-tenancy, no
inbound listener) · A02 findings · A03 findings · A04 clean (no app crypto;
TLS verification defaults retained; no weak hashing for security purposes) ·
A05 clean (no SQL/template/shell-injection sinks; subprocess uses argv list
with `shell=False`) · A06 N/A (no business logic / accounts) · A07 N/A (no
auth) · A08 findings (residual SB3 deserialization opt-out) · A09 clean (no
secret/PII logging observed; logs go to stderr only) · A10 clean (errors are
contained, no client-facing surface to leak stack traces).

## Executive Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 2 |
| Low | 1 |
| Informational | 3 |

An attacker today gains no foothold from a default install: SB3
trusted-repo enforcement now fails closed, Hugging Face downloads are pinned
to a commit revision, VLM sidecar binding refuses non-loopback hosts without
explicit acknowledgement, and `dev`/`runp` containers run with
`no-new-privileges` and `cap_drop: ALL`. The two remaining Medium items —
the writable `.:/app` bind mount on the editing-oriented Compose services and
the operator opt-out path back into permissive SB3 loading — were both
deliberate residual risks recorded in the prior audit's decision; they are
re-confirmed here, not newly identified. **The single most important action
this week is to add a scheduled `pip-audit` (or equivalent) CI job** so
downstream CVEs against the hash-pinned `requirements.txt` get observed
without requiring an operator to run the on-demand `audit` Compose service.

## Verification of 2026-05-07 Remediations

Each remediation claimed by the prior audit was re-checked against current
code:

| Prior finding | Status | Evidence |
|---|---|---|
| #1 SB3 trusted-repo enforcement default | **VERIFIED** | `enforce_trusted_repo: bool = True` in [docugym/config.py](docugym/config.py#L65); `enforce_trusted_repo: true` in [configs/default.yaml](configs/default.yaml#L17); fail-closed branch in [docugym/env.py](docugym/env.py#L165-L189). |
| #2 HF revision pinning in `_download_policy` | **VERIFIED** | `hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)` in [docugym/env.py](docugym/env.py#L182-L190); shipped preset `sb3_revision: "c0741d2e949614ef905e2489241c3032d1c9cce3"` in [configs/default.yaml](configs/default.yaml#L15). |
| #3 Voice/VLM extras in lock + hash export | **VERIFIED** | `voice` and `vlm` optional groups in [pyproject.toml](pyproject.toml#L35-L42); `kokoro`, `sounddevice`, `soundfile`, `vllm` present in [requirements.txt](requirements.txt) with `--hash=sha256:` lines. |
| #4 `dev`/`runp` capability + privilege barriers | **VERIFIED (residual writable mount retained by design)** | `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]` on both services in [docker-compose.yaml](docker-compose.yaml#L17-L21) and [docker-compose.yaml](docker-compose.yaml#L49-L53); `volumes: - .:/app` (writable) retained at [docker-compose.yaml](docker-compose.yaml#L22-L23). |
| #5 VLM sidecar non-loopback gate | **VERIFIED** | `if [[ "${DOCUGYM_VLM_ALLOW_PUBLIC:-}" != "1" ]]; then ... exit 2` in [scripts/serve_vlm.sh](scripts/serve_vlm.sh#L8-L21). |

## Medium Findings

### 1. Operator opt-out reintroduces SB3 deserialization RCE

- **Location:** [docugym/env.py](docugym/env.py#L165-L189), [docugym/config.py](docugym/config.py#L29-L65), [docugym/cli.py](docugym/cli.py#L487-L520) | **Severity:** Medium | **Confidence:** High
- **Exploitability:** Medium | **CWE:** CWE-502 | **OWASP 2025:** A08

Defaults are now safe, but the warning-only path is still reachable. With
`agent.enforce_trusted_repo: false` (or by combining a custom repo id without
adjusting the trusted prefix list), the loader downgrades to a logger warning
and proceeds to deserialize the artifact through `stable_baselines3.PPO.load`,
which under the hood unzips and `pickle`-loads the policy:

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

`_download_policy` does carry the `revision` parameter through, but a
custom-repo override that omits a revision still resolves to current `HEAD`:

```python
downloaded_path = Path(
    hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)
)
```

**Attack path:** operator chases an SB3 reference checkpoint not under the
`sb3/` prefix → adds `enforce_trusted_repo: false` to bypass the new default
or passes `--repo-id` with a custom trusted prefix list → resolver fetches
mutable `HEAD` of the third-party repo → maintainer takeover or typo-squat
publishes a poisoned `.zip` → `PPO.load` deserializes pickle blob → arbitrary
code in the operator's user context.
**Impact:** local RCE in the operator's user context (full `~/`, SSH keys, the
writable repo bind mount inside the dev container).
**Remediation:** require an interactive `typer.confirm()` prompt (or an
explicit `--allow-untrusted-repo` flag) at CLI boundary whenever
`enforce_trusted_repo` is `false` *or* the resolved repo id is outside the
trusted prefix list, and refuse to proceed with a custom repo id that has no
`sb3_revision` / `--revision` pin. Carrying the same fail-closed posture into
the CLI prevents a single YAML edit from re-enabling the warning-only loader.
This is the partially-mitigated continuation of the 2026-05-07 audit's
finding #1.

### 2. Writable host bind mount on `dev` and `runp` Compose services

- **Location:** [docker-compose.yaml](docker-compose.yaml#L22-L23), [docker-compose.yaml](docker-compose.yaml#L54-L55) | **Severity:** Medium | **Confidence:** High
- **Exploitability:** Medium | **CWE:** CWE-732 | **OWASP 2025:** A02

Both `dev` and `runp` mount the repository writable into the container; their
new `no-new-privileges:true` and `cap_drop: ALL` defenses prevent privilege
expansion *inside* the container but do not stop in-container code from
writing the host-visible source tree:

```yaml
volumes:
  - .:/app
working_dir: /app
```

Compare to the hardened `audit` service which uses `:ro` and `read_only: true`.
Any code running inside `dev`/`runp` (an installed dependency, a `pre-commit`
hook, a malicious model load that survived finding 1's opt-out path) can
rewrite `.git/hooks/post-commit`, drop a backdoor in
`docugym/__init__.py`, or modify `pyproject.toml` to fetch attacker
dependencies on the next `uv sync`.
**Attack path:** in-container RCE via finding 1's opt-out or a typo-squatted
dependency → process writes to `/app/.git/hooks/post-commit` or
`/app/docugym/__init__.py` → next host-side `git commit` or `python -m
docugym` runs the implant outside the container boundary.
**Impact:** container-to-host repository tampering and persistence.
**Remediation:** ship a `compose --profile readonly` overlay (or `runp-ro`
service) that mounts `.:/app:ro` and sets `read_only: true` for non-edit
workflows; keep the writable mount only on `dev`. This finding has been
carried in [cdoc/security-audit-and-risk-register.md](cdoc/security-audit-and-risk-register.md) for several iterations and
remains the chosen residual.

## Low Findings

### 3. No scheduled CVE scan against the hash-pinned `requirements.txt`

- **Location:** [.github/workflows/ci.yml](.github/workflows/ci.yml#L1-L46), [.github/workflows/zizmor.yml](.github/workflows/zizmor.yml#L1-L25), [docker-compose.yaml](docker-compose.yaml) (`audit` service) | **Severity:** Low | **Confidence:** High
- **Exploitability:** Low | **CWE:** CWE-1104 | **OWASP 2025:** A06

CI runs only `ruff check` and `pytest`; no dependency vulnerability scanner
runs on push, on PR, or on a schedule:

```yaml
- name: Ruff check
  run: uv run ruff check .

- name: Pytest
  run: uv run pytest -q
```

`pip-audit` exists only as an opt-in `audit` Compose service that an operator
must invoke locally. Dependabot is configured for version updates but does
not function as a CVE alerter against the active export. Combined with the
strict `--require-hashes` posture (which is intentional and correct), a
known-CVE version of a transitive dependency can stay pinned in
`requirements.txt` indefinitely until an operator manually runs the audit
container or until Dependabot opens an unrelated bump.
**Attack path:** post-disclosure of a CVE against (e.g.) `vllm`,
`stable-baselines3`, `httpx`, or a transitive of `kokoro` → docugym continues
installing the vulnerable hashed pin in CI and to operators' venvs → no
automated signal until the next manual `docker compose run audit` or
unrelated bump.
**Impact:** prolonged exposure window for known-CVE dependencies; supply-chain
risk realized via a vulnerability rather than a takeover.
**Remediation:** add a scheduled GitHub Actions workflow (`schedule:` cron
weekly, plus PR trigger) that runs `pip-audit -r requirements.txt
--disable-pip` (or `uv tool run pip-audit`) and fails the job on any
non-suppressed advisory; pin the action and any audit tool to a full SHA;
upload SARIF if convenient. Keep the on-demand `audit` Compose service for
local repro.

## Informational

### 4. ffmpeg argv lacks `--` end-of-options separator before operator-controlled output paths

- **Location:** [docugym/recording.py](docugym/recording.py#L189-L211), [docugym/recording.py](docugym/recording.py#L243-L271) | **Severity:** Informational | **Confidence:** High

Both the encoder `Popen` and the mux `subprocess.run` end with
`str(self._out_path)` (and `str(self._video_path)` / `str(self._audio_path)`)
as bare positional arguments without an `--` end-of-options sentinel:

```python
command = [
    self._ffmpeg_binary,
    ...
    str(self._video_path),
]
self._video_process = subprocess.Popen(command, stdin=subprocess.PIPE, ...)
```

Tempfile paths are produced by `TemporaryDirectory(prefix="docugym-recording-")`
so they cannot start with `-`, and the operator-controlled `out_path` flows
in from CLI/config under the operator's own trust. There is no attacker
input here under the stated threat model, so this is not a finding — but
adding `"--"` before the final positional argument is a free defense in depth
that keeps a future refactor (e.g. accepting the output path from a
less-trusted source) safe by construction.

### 5. VLM narration text is treated as untrusted by display/TTS/clip sinks but is not separately documented

- **Location:** [docugym/clips.py](docugym/clips.py#L51-L60), [docugym/recording.py](docugym/recording.py#L100-L130), [docugym/narrator.py](docugym/narrator.py#L155-L170) | **Severity:** Informational | **Confidence:** Medium

Narration strings from the multimodal VLM (potentially influenced by
adversarial frame content via prompt-injection style attacks) are written to
PNG-pair text files in `out/clips/`, mirrored into TTS audio, and included
in the recorded MP4 audio track:

```python
narration_path.write_text(f"{narration.strip()}\n", encoding="utf-8")
```

There is no current sink that interprets narration as code, markup, a shell
argument, or a log-injection vector — `narration` is not passed to any
`logger.*` call, never reaches `subprocess`, and is rendered through PyGame
text APIs that do not interpret control codes. The trust posture is
correct; however, the assumption "narration is data, never code" is
load-bearing and not documented as a security invariant. Future work that
routes narration into shell tooling, browser UI, or templated emails should
re-evaluate sanitization. No remediation needed today.

### 6. Subprocess, YAML, JSON, dynamic-import, and outbound-HTTP hygiene confirmed clean

- **Locations:** [docugym/recording.py](docugym/recording.py#L207-L213), [docugym/cli.py](docugym/cli.py#L141-L165), [docugym/cli.py](docugym/cli.py#L86-L96), [docugym/narrator.py](docugym/narrator.py#L90-L95), [requirements.txt](requirements.txt), [.github/workflows/ci.yml](.github/workflows/ci.yml#L17-L29) | **Severity:** Informational | **Confidence:** High

Re-verified clean signals: `subprocess` calls use argv lists with `shell=False`
and a `shutil.which`-resolved binary; YAML config is parsed exclusively with
`yaml.safe_load`; CLI JSON input runs through `json.loads` with an
`isinstance(parsed, dict)` guard; `importlib.import_module` is only invoked
with hardcoded module names for lazy optional-dep loading; `httpx.URL`
validates the configured `base_url` scheme is `http`/`https` with a host
before the client is ever used; no `verify=False`, no `eval`/`exec`/`compile`,
no `pickle.load`/`torch.load`/`yaml.load`, no `os.system`/`os.popen`/
`shell=True`, no `tempfile.mktemp`. CI actions and pre-commit hooks are
pinned to full commit SHAs with same-line version comments;
`requirements.txt` is exported with `--hash` lines and CI fails on lock
drift. No remediation needed.

## Phase 4 — Secrets sweep

A dedicated grep + hand inspection of `docugym/`, `configs/`, `tests/`,
`scripts/`, `.github/`, and root configuration files turned up no
hardcoded API keys, tokens, passwords, or private-key material. No `.env`
file is tracked in VCS; `betterleaks` runs in pre-commit with a strict
`AND`-allowlist tuned to deterministic hash-pinning false positives. No
PII/PHI/PCI is processed. The only credential-shaped strings present are
SHA-256 hashes in `requirements.txt`, full Git SHAs pinning CI actions and
pre-commit hooks, and the `sb3_revision` commit SHA in `configs/default.yaml`
— all of which are integrity pins, not secrets.

## Non-security observations

- `_video_stderr_chunks` in [docugym/recording.py](docugym/recording.py#L65-L70) is an unbounded `list[bytes]`; under a long-running recording with a chatty ffmpeg build, this grows without limit. Functional/quality issue, not a security finding under the stated threat model.

## Nothing else found

- A01 Broken Access Control / SSRF: no auth, no multi-tenancy, no inbound listener, no user-controlled URLs reaching outbound HTTP — the only outbound destination is the configured `vlm.base_url`, validated as absolute http(s).
- A04 Cryptographic Failures: no application-level crypto. TLS verification uses httpx defaults (enabled). Integrity for downloaded model weights is now revision-pinned for shipped presets; `requirements.txt` is hash-pinned.
- A05 Injection: no SQL, no NoSQL, no LDAP, no XPath, no template engines, no shell expansion of user input.
- A06 Insecure Design: no accounts, no rate-limited endpoints, no business workflow.
- A07 Authentication Failures: no auth.
- A09 Logging & Alerting: no PII logging; logs go to stderr; no log sink the app could exhaust or have rotated by an attacker. (See remediation 3 for missing CVE *alerting* on dependencies.)
- A10 Exception Handling: errors do not leak to a remote client (no inbound listener); `subprocess` failures are wrapped into `RuntimeError` with sanitized stderr; no fail-open authorization.

## Summary Table

| # | Title | Severity | Confidence | Exploitability | CWE | OWASP |
|---|---|---|---|---|---|---|
| 1 | Operator opt-out reintroduces SB3 deserialization RCE | Medium | High | Medium | CWE-502 | A08 |
| 2 | Writable host bind mount on `dev` and `runp` | Medium | High | Medium | CWE-732 | A02 |
| 3 | No scheduled CVE scan against hash-pinned requirements | Low | High | Low | CWE-1104 | A06 |
| 4 | ffmpeg argv lacks `--` end-of-options separator | Informational | High | — | — | — |
| 5 | Narration-as-data invariant undocumented | Informational | Medium | — | — | — |
| 6 | Subprocess/YAML/JSON/dyn-import/HTTP hygiene clean | Informational | High | — | — | — |
