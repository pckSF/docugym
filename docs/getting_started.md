# Getting Started

This guide gets DocuGym running locally for both CLI and library workflows.

## Prerequisites

- Python 3.11 or 3.12.
- Linux desktop environment for display output.
- Optional NVIDIA GPU for high-throughput local VLM inference.
- `ffmpeg` in `PATH` if you plan to record MP4 output.

## Install

Install the package into your active environment:

```bash
python3 -m pip install .
```

Optional extras:

```bash
python3 -m pip install ".[vlm]"
python3 -m pip install ".[voice]"
python3 -m pip install ".[vlm,voice]"
```

If you use uv-managed environments:

```bash
uv pip install .
uv pip install ".[vlm,voice]"
```

## Baseline Sanity Checks

Check packaged presets and voices:

```bash
docugym list-envs
docugym list-voices
```

Print effective merged settings:

```bash
docugym show-config --config default
```

## Start the Narration Backend

Start the bundled local sidecar script:

```bash
scripts/serve_vlm.sh
```

If startup takes longer than expected, run commands with readiness polling:

```bash
docugym run --config atari --wait-for-vlm --wait-timeout 120
```

## First Narrated Run

Run with subtitle-only narration (default):

```bash
docugym run --config atari --wait-for-vlm
```

Run with voice enabled:

```bash
docugym run --config atari --voice --wait-for-vlm
```

Override environment and policy at runtime:

```bash
docugym run \
  --config atari \
  --env ALE/Pong-v5 \
  --policy sb3/ppo-PongNoFrameskip-v4 \
  --wait-for-vlm
```

## Security Flags for Custom SB3 Repositories

Loading arbitrary SB3 checkpoints can execute untrusted code during
deserialization. For non-allowlisted repositories, pin a revision and opt in
explicitly:

```bash
docugym run \
  --repo-id <owner>/<policy-repo> \
  --filename <policy-file>.zip \
  --revision <commit-sha> \
  --allow-untrusted-repo \
  --yes
```

## Recording

Install ffmpeg if needed:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

Record a session:

```bash
docugym run --config atari --record out/session.mp4 --wait-for-vlm
```

## Wrapper-Mode Quickstart (Library API)

```python
import gymnasium as gym

from docugym import docuwrapper

env = gym.make("CartPole-v1", render_mode="rgb_array")
env = docuwrapper(env, env_id="CartPole-v1", voice_enabled=False)

obs, info = env.reset(seed=42)
for _ in range(200):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        obs, info = env.reset()

env.close()
```

See [Library Integration Guide](library_guide.md) for callback hooks and runtime
state diagnostics.
