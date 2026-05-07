# DocuGym

DocuGym is a fully local desktop application that watches a live Gymnasium game,
turns key moments into calm nature-documentary narration, and speaks that narration
alongside gameplay. The project targets a single-machine setup (RTX 3090 Ti class)
with local inference for both vision-language narration and text-to-speech.

The long-term goal is a smooth, game-window-first viewing experience where narration
lags gameplay by about one to two seconds but still feels synchronized and informative.

## Quickstart (Stage 8)

1. Install project dependencies:

```bash
uv sync
```

2. Start the local VLM sidecar:

```bash
scripts/serve_vlm.sh
```

3. In another terminal, run with a preset config:

```bash
docugym run --config configs/atari.yaml --wait-for-vlm
```

4. Run subtitle-only narration when you want lower compute or silent playback:

```bash
docugym run --config configs/lunarlander.yaml --no-voice --wait-for-vlm
```

5. Override config values from the command line when needed:

```bash
docugym run \
  --config configs/atari.yaml \
  --env ALE/Pong-v5 \
  --policy sb3/ppo-PongNoFrameskip-v4 \
  --wait-for-vlm

6. Record a narrated run to MP4 (optional Stage 9):

```bash
docugym run --config configs/atari.yaml --record out/session.mp4 --wait-for-vlm
```
```

The `run` command renders the live PyGame window, keeps gameplay smooth with the
Stage 6 async pipeline, and updates subtitles from narration text returned by the
local OpenAI-compatible VLM endpoint.

## Presets and Discovery Commands

- `docugym list-envs`: show supported Stage 8 preset configs and their effective env/policy.
- `docugym list-voices`: show Kokoro's 8 British voices and sample lines.
- `docugym run --config configs/carracing.yaml`: start from a Box2D preset.

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
	about 1 GB runtime overhead. Reduce model size or disable voice
	(`--no-voice`) if memory pressure is high.
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
