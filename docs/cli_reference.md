# CLI Reference

DocuGym uses a Typer-based CLI with a single root command group and one nested
`tune` subgroup.

## Root Command

```bash
docugym [OPTIONS] COMMAND [ARGS]...
```

Global options:

- `--config, -c`: YAML path or packaged preset name (`default`, `atari`,
  `lunarlander`, `carracing`).
- `--log-level`: Python logging level (`INFO` default).

## Commands

## show-config

Prints effective merged configuration as JSON.

```bash
docugym show-config --config atari
```

## list-envs

Lists packaged presets and associated default policy hints.

```bash
docugym list-envs
```

## list-voices

Lists curated Kokoro voice IDs with sample phrases.

```bash
docugym list-voices
```

## smoketest

Captures rendered PNG frames for environment/policy/render validation.

```bash
docugym smoketest --env CartPole-v1 --steps 120 --agent random
```

Key options:

- `--env`, `--seed`, `--steps`, `--out-dir`
- `--agent` (`random`, `scripted`, `sb3`)
- `--repo-id`, `--filename`, `--revision`
- `--allow-untrusted-repo`, `--yes`
- `--env-kwargs` (JSON object)

## display-smoketest

Runs display-only validation without narration or TTS.

```bash
docugym display-smoketest --env CartPole-v1 --fps 60 --window-scale 2
```

Key options:

- `--env`, `--seed`, `--fps`, `--steps`
- `--window-scale`, `--min-window-width`
- `--subtitle`, `--subtitle-max-text-width`
- `--hud/--no-hud`
- `--text-bands/--overlay-text`
- `--env-kwargs` (JSON object)

## run

Runs the full narrated session pipeline.

```bash
docugym run --config atari --wait-for-vlm
```

Common options:

- Runtime/display: `--env`, `--seed`, `--fps`, `--steps`, `--window-scale`,
  `--min-window-width`, `--subtitle-max-text-width`, `--hud/--no-hud`,
  `--text-bands/--overlay-text`
- Narration pacing: `--narrate-every`
- Agent/policy: `--agent`, `--policy`, `--repo-id`, `--filename`, `--revision`
- Security: `--allow-untrusted-repo`, `--yes`
- Voice/recording: `--voice/--no-voice`, `--record`
- Backend readiness: `--wait-for-vlm`, `--wait-timeout`
- Env construction: `--env-kwargs` (JSON object)

Examples:

```bash
# Subtitle-only default
docugym run --config default --wait-for-vlm

# Voice opt-in
docugym run --config default --voice --wait-for-vlm

# Record MP4
docugym run --config atari --record out/session.mp4 --wait-for-vlm
```

## tune prompt

Collects narrated samples at fixed step strides for prompt iteration.

```bash
docugym tune prompt --env ALE/SpaceInvaders-v5 --samples 20 --step-stride 5
```

Key options:

- `--env`, `--seed`, `--samples`, `--step-stride`
- `--agent`, `--policy`, `--repo-id`, `--filename`, `--revision`
- `--allow-untrusted-repo`, `--yes`
- `--wait-for-vlm`, `--wait-timeout`
- `--env-kwargs`

## Security Notes

When loading SB3 models from outside trusted repository prefixes:

- Provide `--revision` to pin source state.
- Pass `--allow-untrusted-repo`.
- Use `--yes` for non-interactive CI flows.

## Discovery

Inspect command-specific help:

```bash
docugym --help
docugym run --help
docugym tune prompt --help
```
