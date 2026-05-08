# DocuGym

[![Version](https://img.shields.io/badge/version-0.1.0-blue)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-92%20passed-brightgreen)](tests)
[![Lint](https://img.shields.io/badge/lint-ruff%20passing-brightgreen)](pyproject.toml)
[![Docs](https://img.shields.io/badge/docs-strict%20quality%20passing-brightgreen)](docs/documentation_contract.md)
[![Install Smoke](https://img.shields.io/badge/install%20smoke-passing-brightgreen)](README.md#installation)

DocuGym is a fully local desktop application that turns live Gymnasium runs into
nature-documentary-style experiences with synchronized subtitles and optional voice.
It is designed for single-machine execution with local VLM narration and local TTS.

If you can render a Gym frame, DocuGym can narrate it.

This project was an experiment in pure agentic coding without any manual code
interaction; every change, no matter how small, had to go through an agent.
DocuGym is something I always wanted but never needed, which made it the
perfect excuse to finally try the experiment.


## Table of Contents

- [Why DocuGym](#why-docugym)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Architecture Snapshot](#architecture-snapshot)
- [Run Modes](#run-modes)
- [CLI Command Map](#cli-command-map)
- [Prompt Tuning](#prompt-tuning)
- [Runtime Shortcuts](#runtime-shortcuts)
- [Recording](#recording)
- [Troubleshooting](#troubleshooting)
- [Development Workflow](#development-workflow)
- [Reference Docs](#reference-docs)
- [Documentation Quality Standard](#documentation-quality-standard)
- [Design and Decision Logs](#design-and-decision-logs)

## Why DocuGym

DocuGym exists for sessions where silent gameplay is hard to interpret in real time.
It narrates key events without requiring cloud APIs and keeps playback responsive by
using bounded queues and asynchronous orchestration.

Primary use cases:
- Live narrated evaluation runs for RL environments.
- Prompt and model iteration for narration style.
- Wrapper-mode integration into existing Gym control loops.

## System Requirements

- Python 3.11+.
- Linux workstation with an NVIDIA GPU recommended for local VLM + TTS.
- `ffmpeg` in `PATH` for optional MP4 recording.
- Optional: a local OpenAI-compatible endpoint (for example vLLM) for narration.

## Installation

1. Clone the repository, enter the checkout, and install into your active Python
environment:

```bash
git clone <repo-url> docugym
cd docugym
python3 -m pip install .
```

With uv, install the project into the selected environment with:

```bash
uv pip install .
```

2. Install optional extras when the same environment should also host VLM or voice
runtime dependencies:

```bash
python3 -m pip install ".[vlm]"
python3 -m pip install ".[voice]"
python3 -m pip install ".[vlm,voice]"
```

Use `uv pip install ".[vlm,voice]"` for the equivalent uv environment install.

3. Install system dependency for recording when you want MP4 output:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

For repository development, use `uv sync --extra vlm --extra voice` instead of
`uv pip install .`; `uv sync` creates and maintains the checkout's development
environment.

## Quickstart

1. Start the local VLM sidecar:

```bash
scripts/serve_vlm.sh
```

2. Start a narrated run from a packaged preset:

```bash
docugym run --config atari --wait-for-vlm
```

Editable YAML files still work from a checkout, for example
`docugym run --config configs/atari.yaml --wait-for-vlm`.

3. Enable voiced narration when you want audio (opt-in):

```bash
docugym run --config lunarlander --voice --wait-for-vlm
```

4. Override environment or policy at runtime:

```bash
docugym run \
	--config configs/atari.yaml \
	--env ALE/Pong-v5 \
	--policy sb3/ppo-PongNoFrameskip-v4 \
	--wait-for-vlm
```

5. Record to MP4:

```bash
docugym run --config atari --record out/session.mp4 --wait-for-vlm
```

## Architecture Snapshot

DocuGym runtime keeps gameplay smooth by decoupling frame production from narration
and speech generation.

```text
Gym Env -> Frame Stream -> Keyframe Selector -> Narrator (VLM)
	 |                               |                 |
	 |                               v                 v
	 +------------------------> Display <------ Subtitle/Text
																	 |
																	 v
												 Optional TTS -> Audio Output
																	 |
																	 v
													 Optional MP4 Recorder
```

Key properties:
- Freshness-biased queues drop stale narration work under pressure.
- Display updates are independent from narration latency.
- Voice is optional and can be toggled at runtime.

## Run Modes

### CLI Run Mode

Use `docugym run` for production-like narrated sessions, preset-driven workflows,
and recording.

With the default config, CLI runs start in subtitle-only mode
(`tts.enabled: false`). Use `--voice` when you want spoken narration.

### Wrapper Mode

Use wrapper mode when you need Gym-style `reset`/`step` control flow.

```python
import gymnasium as gym

from docugym import docuwrapper

env = gym.make("CartPole-v1", render_mode="rgb_array")
env = docuwrapper(
		env,
		env_id="CartPole-v1",
		voice_enabled=False,
		narration_interval_seconds=3.0,
		reward_spike_threshold=0.5,
)

obs, info = env.reset(seed=42)
for _ in range(300):
		action = env.action_space.sample()
		obs, reward, terminated, truncated, info = env.step(action)
		if terminated or truncated:
				obs, info = env.reset()

env.close()
```

Library users can also tune the default narration prompt before constructing a
narrator or wrapper:

```python
from docugym import reset_system_prompt, set_system_prompt

set_system_prompt("Narrate with terse, analytical field notes.")
# Create VLMNarrator or docuwrapper(...) here.
reset_system_prompt()
```

Wrapper behavior notes:
- It preserves Gym-style action loop semantics.
- It adds live diagnostics in `info["docugym"]`.
- It supports callbacks for narration, subtitles, audio chunks, and status.

## CLI Command Map

- `docugym list-envs`: print packaged presets and policy hints.
- `docugym list-voices`: print curated Kokoro voice ids and samples.
- `docugym show-config`: print effective merged settings JSON.
- `docugym smoketest`: capture PNG frames for render/path validation.
- `docugym display-smoketest`: validate rendering without narration/TTS.
- `docugym run`: execute full narrated session pipeline.
- `docugym tune prompt`: collect fixed-stride narration samples.

## Prompt Tuning

Collect comparable narration samples:

```bash
docugym tune prompt --env ALE/SpaceInvaders-v5 --samples 20 --wait-for-vlm
```

High-leverage flags:
- `--step-stride`: wider scene diversity across samples.
- `--seed`: reproducible frame sampling for A/B runs.
- `--policy` or `--agent`: align tuning path with runtime behavior.

### Narrative Style Tuning

1. Try a different voice:

```yaml
tts:
	kokoro:
		voice: "bm_fable"
```

2. Space out narration for calmer pacing:

```yaml
narration:
	interval_seconds: 4.0
	min_gap_seconds: 2.0
```

3. Pick model size by quality and latency budget:

```yaml
vlm:
	model: "Qwen/Qwen3-VL-4B-Instruct"
```

Model guidance:
- `Qwen/Qwen3-VL-4B-Instruct`: lower memory, faster responses.
- `Qwen/Qwen3-VL-8B-Instruct-AWQ`: higher quality baseline.

## Runtime Shortcuts

- `space`: pause or resume environment stepping.
- `n`: force narration on current frame.
- `m`: mute or unmute voiced narration.
- `s`: save frame + narration clip snapshot to `out/clips/`.

## Recording

- Use `--record out/session.mp4` for combined gameplay + narration audio.
- If `recording.enabled: true` is set, `recording.out_path` is used by default.
- Recording requires `ffmpeg` on the system path.

## Troubleshooting

- Sidecar startup looks slow:
	first model load may take around 60-120 seconds. Use `--wait-for-vlm` and raise
	`--wait-timeout` when needed.
- GPU memory pressure:
	keep subtitle-only mode (default), or disable voice with `--no-voice` if you
	explicitly enabled it with `--voice`.
- First narration is delayed:
	this is usually model prefill cost; warm up sidecar before long sessions.
- SB3 checkpoint mismatch:
	checkpoint env ids are often version-specific (`*NoFrameskip-v4`, `v2`, and so on).
- Recording fails immediately:
	verify `ffmpeg` is installed and available in `PATH`.

## Development Workflow

Run quality checks locally:

```bash
python3 scripts/check_doc_quality.py --strict docugym tests
uv run ruff check .
uv run pytest -q
```

Pre-commit also runs doc-quality, lint, formatting, type checks, and tests.

## Reference Docs

- API entrypoints and callback contracts: `docs/api_reference.md`
- Configuration schema and defaults: `docs/config_reference.md`

## Documentation Quality Standard

Documentation policy and expected depth are defined in `docs/documentation_contract.md`.

The doc-quality checker validates:
- Presence coverage (module/class/public callable).
- Required section headers (`Args`, `Returns`, `Raises`) when applicable.
- Documentation depth levels: `bare`, `minimal`, `standard`, `rich`.

Default level thresholds:
- Core code: `standard` minimum.
- Tests: `minimal` minimum.

## Design and Decision Logs

- Architecture and implementation plan: `specification.md`
- Decision and audit log history: `cdoc/`
