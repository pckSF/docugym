# DocuGym

DocuGym is a fully local desktop application that watches a live Gymnasium game,
turns key moments into calm nature-documentary narration, and speaks that narration
alongside gameplay. The project targets a single-machine setup (RTX 3090 Ti class)
with local inference for both vision-language narration and text-to-speech.

The long-term goal is a smooth, game-window-first viewing experience where narration
lags gameplay by about one to two seconds but still feels synchronized and informative.

## Stage 4 Quickstart

1. Start the local VLM sidecar:

```bash
scripts/serve_vlm.sh
```

2. In another terminal, run the app with synchronous narration every 60 frames:

```bash
docugym run \
	--env ALE/Pong-v5 \
	--policy sb3/ppo-PongNoFrameskip-v4 \
	--narrate-every 60 \
	--wait-for-vlm
```

The `run` command renders the live PyGame window and sends one selected frame
per interval to the local OpenAI-compatible endpoint at `vlm.base_url`. Returned
narration text is shown in subtitles and logged with per-call latency.

## Useful Flags

- `--narrate-every`: fixed frame cadence for Stage 4 synchronous narration.
- `--wait-for-vlm`: poll `/models` until the sidecar is ready.
- `--wait-timeout`: readiness timeout in seconds.
- `--policy`: shorthand for SB3 Hugging Face repo id; implies `--agent sb3`.
- `--env-kwargs`: JSON object forwarded to `gym.make(...)`.
