# specification.md

# Attenborough Live Narrator for Gymnasium — Fully Local Spec

> **To the coding agent:** This document is a *strong recommendation*, not a contract.
> If during implementation you find a better model, library, or pattern — or the
> recommended one breaks, is unmaintained, or performs worse than advertised — you are
> empowered and expected to deviate. Document the deviation in a short ADR-style
> comment in the repo (`/docs/decisions/NNNN-*.md`) and move on. Prefer working
> software to adherence to this spec. This reminder is repeated at every stage boundary.

---

## 1. Overview & goals

Build a desktop application that runs a game-like Gymnasium environment, captures each
rendered frame, generates a short David-Attenborough-style nature-documentary
narration from that frame, and speaks it aloud via TTS — live, alongside the
gameplay display. **Everything runs locally on a single NVIDIA RTX 3090 Ti (24 GB).**

Target environments are **game-like Gymnasium envs only**: Atari/ALE (via `ale-py`),
classic control (`CartPole-v1`, `MountainCar-v0`, `Acrobot-v1`, `Pendulum-v1`),
Box2D (`LunarLander-v3`, `CarRacing-v3`, `BipedalWalker-v3`). MuJoCo and pure-physics
sims are explicitly out of scope.

Success = a viewer sees a game window, hears a calm British narrator describing what's
happening with ~1–2 s of narration lag, and narration-start-to-audio is under ~1.5 s.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Main process (asyncio event loop)                                   │
│                                                                      │
│  ┌──────────────┐   rgb_array   ┌──────────────┐                     │
│  │  Gym env     │ ─────────────▶│  Frame queue │ ── every N frames ─┐│
│  │  + agent     │               │  (bounded)   │  keyframe selector ││
│  └──────┬───────┘               └──────┬───────┘                    ││
│         │                              │ selected frames             ││
│         │                              ▼                             ││
│         │                       ┌──────────────┐                     ││
│         │                       │  VLM client  │  HTTP → vLLM (8000) ││
│         │                       │  (async)     │──────────────────┐  ││
│         │                       └──────┬───────┘                  │  ││
│         │                              │ narration text           │  ││
│         │                              ▼                          │  ││
│         │                       ┌──────────────┐                  │  ││
│         │                       │  Kokoro TTS  │                  │  ││
│         │                       │  (in-proc)   │                  │  ││
│         │                       └──────┬───────┘                  │  ││
│         │                              │ 24 kHz PCM chunks        │  ││
│         │                              ▼                          │  ││
│         ▼                       ┌──────────────┐                  │  ││
│  ┌──────────────┐   frame       │ sounddevice  │◀─audio queue─────┘  ││
│  │  PyGame UI   │◀──────────────│  callback    │                     ││
│  │  display +   │   subtitle    └──────────────┘                     ││
│  │  subtitles   │◀──────────────────────────────────────────────────┘│
│  └──────────────┘                                                    │
└──────────────────────────────────────────────────────────────────────┘

Sidecar process: vLLM server with Qwen3-VL-8B-Instruct-AWQ on CUDA.
```

Two key decoupling points: the env loop **never blocks** on inference, and the audio
callback **never blocks** on the Python interpreter (PortAudio runs in its own C
thread, fed from a lock-free queue).

---

## 3. Tech stack (pinned-ish; deviate if something better appears)

| Layer | Choice | Version | Why |
|---|---|---|---|
| Python | CPython | **3.11** (3.12 OK) | Gymnasium 1.x requires ≥3.10; 3.11 has the most mature wheels |
| Package mgr | **uv** | latest | Fast resolver, native lockfile, first-class PyTorch index support |
| RL env | `gymnasium` | **≥1.2,<2.0** | Current stable; new render-mode API |
| Atari | `ale-py` | **≥0.11** | ROMs bundled; `AtariVectorEnv` available |
| Box2D | `box2d` + `swig` | 2.3+ | `box2d-py` was replaced in Gymnasium 1.1 |
| Pre-trained agents | `stable-baselines3`, `huggingface_sb3`, `rl_zoo3` | latest | SB3 HF org has ready checkpoints |
| VLM (single-pass image→narration) | **`Qwen/Qwen3-VL-8B-Instruct-AWQ`** | Oct 2025 release | Best text fluency at 8B; AWQ fits easily |
| VLM server | **vLLM** | ≥0.10 (Qwen3-VL recipe) | Best single-stream TTFT on a 3090 Ti; OpenAI-compatible API |
| TTS | **Kokoro-82M** (`hexgrad/Kokoro-82M`) | ≥1.0 | Apache-2.0, 8 British voices out of the box, 50–100× real time |
| Display | **PyGame** | ≥2.6 | Used internally by Gymnasium's `HumanRendering`; simple, fast |
| Audio out | **sounddevice** (PortAudio) | latest | Lock-free callback, ~1–10 ms latency |
| Async | `asyncio` + `httpx` | stdlib + latest | vLLM client calls; bounded queues |
| CLI | **Typer** | latest | Clean CLI w/ subcommands |
| Config | **pydantic-settings** | ≥2 | Typed YAML/env-var config |
| Recording (optional) | **ffmpeg** (system) | any | MP4 of screen+audio for sharing |

**Deviation flags:** if Qwen3-VL-8B is too slow for your target FPS, drop to
`Qwen/Qwen3-VL-4B-Instruct` (still excellent prose, ~90 tok/s) or
`Qwen2.5-VL-3B-Instruct-AWQ`. If vLLM gives you trouble with Qwen3-VL, fall back to
**`llama-server --mmproj`** from llama.cpp with `unsloth/Qwen3-VL-8B-Instruct-GGUF`
(UD-Q4_K_XL). If Kokoro's emotional range is too flat, swap in **XTTS v2** (via the
`idiap/coqui-ai-TTS` fork, `coqui-tts` pip) with a licensed British narrator reference
clip, or **Chatterbox-Turbo** (MIT, streaming, fast).

---

## 4. Environment setup

### OS

Linux (Ubuntu 22.04/24.04) is the happy path. Windows 11 works with WSL2 for CUDA;
native Windows works but SDL/PortAudio/pygame DPI quirks are frequent.

### System packages (Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y \
    ffmpeg portaudio19-dev libportaudio2 libsndfile1 \
    swig build-essential pkg-config \
    libsdl2-dev libsdl2-image-dev libsdl2-ttf-dev libsdl2-mixer-dev \
    espeak-ng     # phonemizer backend for Kokoro
```

### CUDA / PyTorch

Install **CUDA 12.4** runtime (via the NVIDIA driver stack) and PyTorch 2.5+.

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install --index-url https://download.pytorch.org/whl/cu124 \
    torch torchvision torchaudio
```

### Python packages

```bash
uv pip install \
    "gymnasium[atari,box2d,classic-control,other]>=1.2,<2.0" \
    "ale-py>=0.11" \
    "stable-baselines3>=2.3" "huggingface_sb3>=3.0" "rl_zoo3>=2.3" \
    "vllm>=0.10" \
    "kokoro>=0.9" "soundfile" "sounddevice" \
    "pygame>=2.6" \
    "pydantic>=2" "pydantic-settings>=2" "typer[all]" "httpx" "pyyaml"
```

### ROM note

No action needed. `ale-py ≥0.8` bundles ROMs; the old `AutoROM` / `ale-import-roms`
workflow is obsolete. Just do `import ale_py; gym.register_envs(ale_py)` once at
process start.

---

## 5. Implementation stages

Each stage is self-contained with a **definition of done (DoD)**. Complete one, commit,
then start the next. At every stage: *you may deviate if a better approach appears.*

### Stage 1 — Scaffolding, config, CI

- Create project `docugym/`, `pyproject.toml` with `uv` lock.
- Add `pydantic-settings`-based config loader (`docugym/config.py`) reading
  `configs/default.yaml`. See §8 for the schema.
- Add `pre-commit` with ruff + black; a minimal GitHub Actions workflow running
  `ruff check` + `pytest -q` on Linux.
- Logging via `structlog` or stdlib `logging` with a friendly format.
- **DoD:** `uv run docugym --help` works; config loads from a YAML and env-var
  overrides work.

### Stage 2 — Gym env wrapper

- Module `docugym/env.py`. Factory `make_env(env_id: str, seed: int) -> gym.Env`
  that (a) calls `import ale_py; gym.register_envs(ale_py)` if `env_id` starts with
  `ALE/`, (b) creates the env with `render_mode="rgb_array"`, (c) supports a dict of
  passthrough kwargs (frameskip, sticky actions).
- Implement a trivial `RandomAgent` and `ScriptedAgent` (e.g., always-go-right for
  MountainCar).
- Add a loader `load_sb3_policy(repo_id, filename) -> Policy` using
  `huggingface_sb3.load_from_hub`. Cache to `~/.cache/docugym/policies/`.
- **Smoke test:** `uv run docugym smoketest --env ALE/SpaceInvaders-v5 --steps 200`
  saves 200 frames to `out/frames/*.png`.
- **DoD:** At least one classic-control, one Box2D, and one Atari env each produce
  non-black frames; `sb3/ppo-LunarLander-v2` checkpoint loads and plays.

### Stage 3 — Display layer

- Module `docugym/display.py` using PyGame. A class `Display` that owns a window,
  pacing `pygame.time.Clock`, a `blit_frame(np.ndarray)` method, a `set_subtitle(str)`
  overlay, and a status bar (env id, step, episode reward).
- Scale frames to a configurable window size (e.g., 3× for Atari's 160×210).
- Do **not** use `pygame.mixer` — audio goes through `sounddevice` in Stage 5.
- **DoD:** A random agent in `ALE/Breakout-v5` runs at 60 FPS with a live window, a
  stub subtitle (hardcoded string), and a visible status bar.

### Stage 4 — Caption/narration via single VLM call (sync first)

- Start vLLM in a sidecar (document a `scripts/serve_vlm.sh`):
  ```bash
  vllm serve Qwen/Qwen3-VL-8B-Instruct-AWQ \
      --max-model-len 4096 \
      --limit-mm-per-prompt '{"image":1,"video":0}' \
      --gpu-memory-utilization 0.70 \
      --mm-processor-cache-gb 0 \
      --dtype auto --port 8000
  ```
  (The 0.70 utilization leaves room for Kokoro and Python.)
- Module `docugym/narrator.py`: an async client that takes `(frame: np.ndarray,
  context: NarrationContext) -> str`. Encode frame as PNG → base64 → OpenAI-style
  multimodal chat message. Use the prompt template in §7.
- Start **synchronous**: call narrator once per N frames from the main loop, paint the
  returned text into the subtitle. Measure p50/p95 latency. Target: ≤1.0 s p50.
- **DoD:** Running `docugym run --env ALE/Pong-v5 --policy sb3/ppo-PongNoFrameskip-v4
  --narrate-every 60` prints a plausible Attenborough-style sentence every ~1 s of
  gameplay. It's okay if gameplay visibly stutters — we'll fix that in Stage 6.

### Stage 5 — Local TTS + streaming audio

- Module `docugym/tts.py`. Load Kokoro once:
  ```python
  from kokoro import KPipeline
  pipe = KPipeline(lang_code='b')   # British English
  # Voices: bm_george (primary), bm_fable, bm_lewis, bm_daniel,
  #         bf_alice, bf_emma, bf_isabella, bf_lily
  ```
- `async def speak(text: str) -> AsyncIterator[np.ndarray]` yields 24 kHz float32
  chunks sentence-by-sentence. Run Kokoro in a worker thread via
  `asyncio.to_thread` — Kokoro itself is sync.
- `audio.py` owns a `sounddevice.OutputStream(samplerate=24000, channels=1,
  dtype='float32', blocksize=0, latency='low', callback=cb)`. `cb` pulls from a
  lock-free `queue.Queue[np.ndarray]` fed by the TTS worker.
- Subtitle queue is fed **per-sentence** with the graphemes (Kokoro yields these
  alongside audio), so subtitles are naturally synced to audio.
- Voice output must be toggleable at runtime (for example, `--voice/--no-voice`),
  while subtitle updates stay enabled in both modes.
  - Reason 1: users may prefer reading subtitles without listening to speech.
  - Reason 2: subtitle-only mode lowers compute demand for weaker systems or when
    fewer resources are available.
  - Reason 3: subtitle-only mode allows cleaner separation of narration and TTS
    testing/build workflows.
- **DoD:** Narration text is audibly spoken in a British voice (`bm_george`), starts
  within ~400 ms of the text being ready, and subtitles change as each sentence
  plays. Audio does not glitch when the env loop runs at 60 FPS.

### Stage 6 — Async orchestration + keyframe selection

- Refactor to a true asyncio pipeline:
  - Task A: env stepping + frame capture → pushes to `frame_q` (maxsize=4,
    drop-oldest on full — the env must not block).
  - Task B: **keyframe selector** consumes `frame_q`, decides if this frame is
    "interesting" and should be narrated. Heuristics (combine, don't OR):
    1. Fixed cadence fallback (`narration_interval_seconds`, default 3.0).
    2. Reward spike: `|reward| > reward_threshold`.
    3. Episode boundary: `terminated or truncated`.
    4. Visual delta: `np.mean(np.abs(curr - prev)) > pixel_threshold` (cheap) — or
       optical-flow magnitude if the cheap version is too noisy.
    5. Cooldown: never narrate closer than `min_narration_gap` (default 1.5 s) to the
       previous.
  - Task C: VLM call (bounded concurrency = 1, the GPU can only do one at a time).
  - Task D: TTS worker (bounded concurrency = 1). Audio chunks → `audio_q`.
  - Task E: sounddevice callback consumes `audio_q` (runs in C thread).
  - Task F: PyGame event loop + subtitle overlay.
- **Backpressure:** if narration + TTS can't keep up, **drop narration candidates**
  (prefer silence over stale commentary). Log drops.
- **Sync strategy:** we narrate a *slightly delayed* timeline. Do **not** slow down
  the env; the viewer is fine with ~1-2 s commentary lag.
- **DoD:** Gameplay is smooth (60 FPS for most envs; Atari at its native ~60 Hz),
  narration triggers on reward spikes + episode ends + fixed cadence, no audio
  dropouts, no deadlocks when you close the window mid-sentence.

### Stage 7 — Subtitles + UI polish

- Subtitle card: semi-transparent black rounded rectangle, white text, 2 lines max,
  auto-wraps.
- Top-left HUD: env id · step · episode reward · "🎙️ narrating" indicator when TTS is
  active · optional tok/s gauge.
- Keyboard shortcuts: `space` pause env, `n` force-narrate current frame, `m` mute
  audio, `s` save current frame + last narration to `out/clips/`.
- **DoD:** A non-technical viewer can watch a 2-minute session and understand
  what's happening without looking at the terminal.

### Stage 8 — Packaging + CLI + README

- Typer CLI:
  - `docugym run --config configs/atari.yaml`
  - `docugym run --env ALE/MsPacman-v5 --policy sb3/ppo-MsPacmanNoFrameskip-v4`
  - `docugym run --env ALE/Pong-v5 --no-voice`  # subtitle-only narration mode
  - `docugym list-voices` — prints Kokoro's 8 British voices + samples
  - `docugym list-envs` — prints supported env presets
- Config presets in `configs/`: `atari.yaml`, `lunarlander.yaml`, `carracing.yaml`.
- README with a 3-minute quickstart and a troubleshooting section that mirrors §6.
- **DoD:** Fresh clone + `uv sync` + `scripts/serve_vlm.sh` + `docugym run
  --config configs/atari.yaml` works on a fresh Ubuntu box.

### Stage 9 (optional) — MP4 recording

- A `--record out/session.mp4` flag. Use ffmpeg as a subprocess: PyGame frames piped
  via `-f rawvideo`; audio tee'd from a parallel `sounddevice.InputStream` loopback
  or from a duplicate PCM buffer. Muxed with `-c:v libx264 -preset ultrafast -crf 20
  -c:a aac -b:a 128k`.
- OBS note: if the user prefers, they can record the pygame window + system audio
  externally via OBS; mention this as a zero-code path.
- **DoD:** `out/session.mp4` plays cleanly with AV-sync drift < 100 ms over 5 min.

### Stage 10 (optional) — Tuning & eval

- `docugym tune prompt --env ... --samples 20` runs 20 narrations over varied frames
  and prints them for prompt A/B.
- Document how to swap in a different voice, change `narration_interval`, or switch
  VLM size.
- **DoD:** A short "how to make it sound more like a nature doc" guide in the README.

---

## 6. Known pitfalls & mitigations

- **vLLM startup is slow** (~60 s first load). Recommend running it as a systemd
  service or `tmux` pane. Add a `--wait-for-vlm` flag that polls `/v1/models`.
- **VRAM OOM under load.** Budget target:
  - vLLM (Qwen3-VL-8B-AWQ, ctx 4K, single stream): ~9–11 GB
  - Kokoro-82M (fp32): ~1.5 GB
  - PyTorch / CUDA overhead: ~1 GB
  - **Total ≈ 12–13 GB, leaving ≥10 GB headroom.**
  If you add optical flow via `torch` → reuse the VLM's torch install.
- **Atari ROM licensing.** Bundled ROMs are provided for research; commercial
  redistribution is a gray area. Do not ship a Docker image containing ROMs. Let the
  user install `ale-py` themselves.
- **Voice cloning ToS.** **Never** attempt to clone David Attenborough's real voice.
  Kokoro's `bm_george` is a generic British narrator — *Attenborough-adjacent in
  tone, not a clone*. The system prompt (§7) says "narrator" not "Attenborough".
- **Sync drift over long sessions.** The narration timeline lags the env timeline
  by `narration_latency`. After ~10 min this is imperceptible to viewers; if it's a
  problem, tighten the keyframe filter so narration is sparser.
- **First-frame latency** (first narration takes ~2 s because VLM prefill is cold).
  Send a warmup request during Stage 2's smoke test.
- **Gymnasium v1 autoreset surprise.** In v1.0+, the step *after* a terminal step
  returns the reset obs with `reward=0` and `terminated=False`; handle this in your
  agent loop.
- **SB3 Zoo checkpoint versioning.** `sb3/ppo-LunarLander-v2` was trained on v2, not
  v3. Register the v2 env explicitly or use `shimmy`. For Atari, stick with
  `*NoFrameskip-v4` ids (not `ALE/*-v5`) when loading these checkpoints.

---

## 7. Prompt templates

### System prompt (single-pass VLM)

```
You are a calm, wonder-filled nature-documentary narrator in the tradition of BBC
wildlife programmes. You are watching a game on screen and narrating it as if it
were a rare scene from the natural world. Observe the creature (or vessel, vehicle,
or figure) on screen with the same reverence you would give a pangolin or a lyrebird.

Rules:
- 1 to 2 sentences, present tense, British phrasing.
- Hushed, measured, slightly awed. Short clauses. No exclamation marks.
- Use biology / ecology metaphors where natural: instinct, territory, courtship,
  peril, lineage, survival, the edge of exhaustion.
- Do not name the game. Do not mention pixels, screens, scores, or controllers.
- Do not name real people. You are *a* narrator, not *the* narrator.
- If nothing has changed, say so gently (e.g., "A pause. The creature gathers
  itself.").
```

### User message (per frame)

```
[image: <base64 PNG>]
Context:
- Scene: {env_human_name}   # e.g., "a small lunar lander approaching its pad"
- Last narration (for continuity): "{previous_narration}"
- Recent events: {event_summary}   # e.g., "reward spike +50; episode step 412"

Narrate this moment.
```

### Fallback two-stage prompts (if you split pipeline)

Caption: `"Describe what you see in one neutral sentence."`
Rewrite: same system prompt as above, user message = the caption + context.

---

## 8. Config schema (YAML, `configs/default.yaml`)

```yaml
run:
  env_id: "ALE/SpaceInvaders-v5"
  env_kwargs: { frameskip: 4, repeat_action_probability: 0.25, full_action_space: false }
  seed: 42
  fps: 60
  max_episodes: 10

agent:
  kind: "sb3"                       # sb3 | random | scripted
  sb3_repo_id: "sb3/ppo-SpaceInvadersNoFrameskip-v4"
  sb3_filename: "ppo-SpaceInvadersNoFrameskip-v4.zip"
  # For Atari SB3 checkpoints you must use the matching NoFrameskip-v4 env,
  # not ALE/*-v5. The runner will auto-switch if agent.kind == "sb3" and
  # env_id is ALE/*.

vlm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen/Qwen3-VL-8B-Instruct-AWQ"
  max_tokens: 80
  temperature: 0.8
  top_p: 0.9
  image_detail: "low"               # downscale frame to ~384 px long edge

narration:
  interval_seconds: 3.0
  min_gap_seconds: 1.5
  reward_spike_threshold: 5.0
  pixel_delta_threshold: 8.0        # mean abs pixel diff 0-255
  max_context_events: 3
  previous_narration_window: 2

tts:
  enabled: true                     # false = subtitle-only narration (no TTS/audio)
  engine: "kokoro"                  # kokoro | xtts | chatterbox
  kokoro:
    voice: "bm_george"              # bm_fable, bm_daniel, bm_lewis, bf_alice...
    speed: 0.95
    sample_rate: 24000
  xtts:
    speaker_wav: "data/voices/british_narrator.wav"   # must be a legally-cloned voice

display:
  window_scale: 3
  subtitle_font: "DejaVu Sans"
  subtitle_size: 22
  hud: true

recording:
  enabled: false
  out_path: "out/session.mp4"
```

---

## 9. Final reminder to the coding agent

You are empowered to deviate. If Qwen3-VL-8B is too slow on your specific card, drop
to 4B. If vLLM's Qwen3-VL recipe breaks on the exact version pinned, try llama.cpp
with `llama-server --mmproj`. If Kokoro's prosody feels wrong for the content, try
Chatterbox-Turbo or XTTS v2. If the pipeline jitters, tune queue sizes and drop
policies first — don't reach for a rewrite. **Ship a working narrator over a perfect
spec.**
