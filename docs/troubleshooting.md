# Troubleshooting

This page covers the most common runtime and setup issues.

## VLM Endpoint Not Ready

Symptoms:

- `docugym run` starts but no narration appears.
- readiness checks time out.

Actions:

1. Ensure the sidecar endpoint is running.
2. Use readiness polling and increase timeout:

```bash
docugym run --config default --wait-for-vlm --wait-timeout 120
```

3. Confirm endpoint URL in effective config:

```bash
docugym show-config --config default
```

## Voice Playback Not Working

Symptoms:

- Narration subtitles appear, but no sound.
- Runtime logs mention voice fallback.

Actions:

1. Install voice extras:

```bash
python3 -m pip install ".[voice]"
```

2. Enable voice explicitly (CLI default is subtitle-only):

```bash
docugym run --config default --voice --wait-for-vlm
```

3. Verify audio device availability on host.

## SB3 Repository Trust Errors

Symptoms:

- CLI refuses to load policy from custom Hugging Face repo.

Actions:

1. Pin model revision (`--revision <commit-sha>`).
2. Explicitly opt in to untrusted repo usage.

```bash
docugym run \
  --repo-id <owner>/<policy-repo> \
  --filename <policy-file>.zip \
  --revision <commit-sha> \
  --allow-untrusted-repo \
  --yes
```

## Recording Fails

Symptoms:

- recording starts then disables itself.
- output MP4 is missing.

Actions:

1. Install ffmpeg:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

2. Verify ffmpeg is discoverable:

```bash
ffmpeg -version
```

3. Confirm recording path is writable.

## Display Window Closes or Freezes

Actions:

1. Use lower rendering workload:

- reduce `--fps`
- reduce `--window-scale`
- disable voice (`--no-voice`) if you previously enabled it

2. Validate rendering path independently:

```bash
docugym display-smoketest --config default --steps 300
```

## Invalid env_kwargs JSON

Symptoms:

- CLI returns a parameter error for `--env-kwargs`.

Action:

Use a valid JSON object string:

```bash
docugym run --env-kwargs '{"frameskip": 4, "repeat_action_probability": 0.1}'
```

## Debugging Checklist

- Print resolved config: `docugym show-config --config <preset-or-path>`
- Test rendering only: `docugym display-smoketest ...`
- Test frame capture path: `docugym smoketest ...`
- Re-run with explicit agent and policy flags.
- Increase log verbosity: `--log-level DEBUG`
