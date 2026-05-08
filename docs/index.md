# DocuGym Documentation

DocuGym is a local-first narration layer for Gymnasium environments. It provides
an interactive narrated runtime, a Gym wrapper API, and a CLI for smoke tests,
interactive sessions, and prompt tuning.

This folder is organized so it can be consumed directly in Markdown or wired into
common static-site pipelines (for example MkDocs, Docusaurus, or MyST-based
Sphinx builds).

## Documentation Map

## Start Here

- [Getting Started](getting_started.md)
- [CLI Reference](cli_reference.md)
- [Troubleshooting](troubleshooting.md)

## Concepts

- [Architecture](architecture.md)
- [Library Integration Guide](library_guide.md)

## Reference

- [API Reference](api_reference.md)
- [Configuration Reference](config_reference.md)
- [Documentation Contract](documentation_contract.md)

## Development

- [Contributing and Quality Gates](contributing.md)

## Product Summary

DocuGym turns rendered frames into near-real-time commentary using an
OpenAI-compatible multimodal endpoint. The runtime preserves responsiveness by
separating rendering from narration work with bounded queues and stale-work
dropping.

Key traits:

- Local execution; no cloud dependency required.
- Subtitle-first default mode, with optional voice output.
- Interactive runtime controls for pause, force narration, mute, and clip saves.
- Security guardrails for SB3 model loading from Hugging Face repos.
- A stable installable package surface for library integrations.

## Quickstart

1. Install the package:

```bash
python3 -m pip install .
```

2. Start the local model sidecar:

```bash
scripts/serve_vlm.sh
```

3. Run a narrated session with a packaged preset:

```bash
docugym run --config atari --wait-for-vlm
```

4. Enable spoken narration explicitly (voice is opt-in):

```bash
docugym run --config atari --voice --wait-for-vlm
```

For complete setup details, see [Getting Started](getting_started.md).
