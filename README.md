# DocuGym

DocuGym is a fully local desktop application that watches a live Gymnasium game,
turns key moments into calm nature-documentary narration, and speaks that narration
alongside gameplay. The project targets a single-machine setup (RTX 3090 Ti class)
with local inference for both vision-language narration and text-to-speech.

The long-term goal is a smooth, game-window-first viewing experience where narration
lags gameplay by about one to two seconds but still feels synchronized and informative.

## Quickstart

1. Install ffmpeg (required for optional recording):

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

2. Install project dependencies, including the local voice and VLM sidecar extras:

```bash
uv sync --extra voice --extra vlm
```

For subtitle-only runs against an already managed VLM endpoint, `uv sync` is enough.

3. Start the local VLM sidecar:

```bash
scripts/serve_vlm.sh
```

The sidecar binds to `127.0.0.1` by default. To bind a non-loopback host, set
both `DOCUGYM_VLM_HOST` and `DOCUGYM_VLM_ALLOW_PUBLIC=1`, and put the endpoint
behind appropriate network controls.

4. In another terminal, run with a preset config:

```bash
docugym run --config configs/atari.yaml --wait-for-vlm
```

5. Run subtitle-only narration when you want lower compute or silent playback:

```bash
docugym run --config configs/lunarlander.yaml --no-voice --wait-for-vlm
```

6. Override config values from the command line when needed:

```bash
docugym run \
	--config configs/atari.yaml \
	--env ALE/Pong-v5 \
	--policy sb3/ppo-PongNoFrameskip-v4 \
	--wait-for-vlm
```

7. Record a narrated run to MP4 (optional):

```bash
docugym run --config configs/atari.yaml --record out/session.mp4 --wait-for-vlm
```

The `run` command renders the live PyGame window, keeps gameplay smooth with an
async pipeline, and updates subtitles from narration text returned by the local
OpenAI-compatible VLM endpoint.

## Presets and Discovery Commands

- `docugym list-envs`: show supported preset configs and their effective env/policy.
- `docugym list-voices`: show Kokoro's 8 British voices and sample lines.
- `docugym run --config configs/carracing.yaml`: start from a Box2D preset.

## Wrapper Mode for Experiments

Use wrapper mode when you want to keep a normal Gymnasium training or control
loop but still get live DocuGym narration and subtitles.

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

Wrapper behavior notes:
- It keeps Gym-style `reset` and `step` usage and always opens the DocuGym window.
- Narration metadata is added to `info["docugym"]` on `reset` and `step`.
- Optional callbacks can be passed at initialization for narration/subtitle/audio/status events.
- `space` pauses frame progression until toggled again, `n` forces narration,
  `m` toggles mute, and `s` saves a clip snapshot.

Use `docugym run` for production runs and recording workflows. Use wrapper mode
for experimentation in custom control loops.

## Tuning and Eval

Use prompt tuning to run narrations over varied frames and compare style changes:

```bash
docugym tune prompt --env ALE/SpaceInvaders-v5 --samples 20 --wait-for-vlm
```

Useful tuning flags:
- `--step-stride`: number of env steps between samples (higher gives more variety).
- `--seed`: repeatable sample sequence for A/B comparisons.
- `--policy` or `--agent`: align tuning with your runtime control path.

### How to make narration sound more like a nature documentary

1. Try a different Kokoro voice:

```yaml
tts:
	kokoro:
		voice: "bm_fable"
```

2. Space out narration to reduce chatter and keep lines more deliberate:

```yaml
narration:
	interval_seconds: 4.0
	min_gap_seconds: 2.0
```

3. Adjust model size for your GPU and style preference:

```yaml
vlm:
	model: "Qwen/Qwen3-VL-4B-Instruct"
```

Model guidance:
- `Qwen/Qwen3-VL-4B-Instruct`: faster and lighter.
- `Qwen/Qwen3-VL-8B-Instruct-AWQ`: higher quality baseline.

Restart the sidecar after changing `vlm.model` so the new model loads.

## Runtime Shortcuts

- `space`: pause or resume environment stepping.
- `n`: force narration for the current frame.
- `m`: mute or unmute voiced narration (subtitles continue).
- `s`: save the current frame and latest narration text to `out/clips/`.

## Recording (Optional)

- Use `--record out/session.mp4` to save gameplay + narration audio as MP4.
- If `recording.enabled: true` is set in your config, `docugym run` records to
	`recording.out_path` unless `--record` overrides it.
- Recording requires a system `ffmpeg` binary in `PATH`.
- Zero-code alternative: you can capture the PyGame window + system audio with OBS.

## Troubleshooting

- vLLM startup appears slow:
	first model load can take around 60-120 seconds. Use `--wait-for-vlm` and
	increase `--wait-timeout` if needed.
- GPU out-of-memory under load:
	budget roughly 9-11 GB for vLLM (Qwen3-VL-8B-AWQ) + 1.5 GB for Kokoro +
	about 1 GB runtime overhead. Reduce model size or disable voice (`--no-voice`)
	if memory pressure is high.
- First narration is noticeably delayed:
	the first request pays model prefill cost. Warm up the sidecar before runs.
- SB3 checkpoint mismatch on Box2D/Atari:
	many SB3 checkpoints are version-specific (for example `ppo-LunarLander-v2`
	and Atari `*NoFrameskip-v4`). Use matching env ids when possible.
- Audio glitches during high narration density:
	increase `narration.interval_seconds` or `narration.min_gap_seconds` to
	reduce synthesis pressure; stale narration candidates are dropped by design.
- Recording fails immediately on startup:
	ensure `ffmpeg` is installed and visible in `PATH`, or run without `--record`.
