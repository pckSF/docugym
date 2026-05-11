---
type: note
tags: [code-review, performance, idiomatic, audit, runtime, wrapper, display, narrator, recording]
created: 2026-05-07
updated: 2026-05-11
status: active
related: [stage-6-async-orchestration-and-keyframe-selection.md, stage-3-display-layer.md, stage-4-vlm-narration-sync.md, stage-5-local-tts-streaming-audio.md, stage-9-mp4-recording.md, wrapper-mode-gym-api-integration.md, final-setup-runtime-and-naming-consolidation.md, 2026-05-07-code-review-remediation-scope.md, 2026-05-11-source-bloat-remediation-pass.md]
---
# Code Review — Idiomatic Issues, Best-Practice Gaps, and Performance Losses

## Context

Repository-wide static review of the Python source under `docugym/` (≈4 300 LoC across 20 modules) on 2026-05-07, after Stage 10 sign-off. Goal: enumerate concrete idiomatic, best-practice, and performance issues with citations and remediation. This note is descriptive — it does **not** mandate fixes. Each item is independently actionable; downstream notes (one per accepted fix) should reference back here.

## Methodology

Every module was read in full (`runtime.py`, `wrapper.py`, `display.py`, `narrator.py`, `recording.py`, `audio.py`, `tts.py`, `env.py`, `cli.py`, `keyframes.py`, `queue_utils.py`, `config.py`, `clips.py`, `tune.py`, `display_actions.py`, `narration_events.py`, `narration_defaults.py`, `logging_config.py`, `__init__.py`, `__main__.py`). Findings are bucketed by severity:

- **H** — correctness or measurable performance regression on the hot path
- **M** — non-idiomatic but bounded impact, or latent bug
- **L** — style/clarity polish

Severity is the reviewer's judgement; the team should reprioritise per their thresholds. Line ranges are 1-indexed and were correct at the time of review (HEAD on 2026-05-07).

## Findings

### docugym/runtime.py

1. **(H) Mutable default in `run_session` parameter list.** [docugym/runtime.py](../docugym/runtime.py#L251-L253) declares `trusted_repo_prefixes: list[str] | tuple[str, ...] = (DEFAULT_TRUSTED_SB3_REPO_PREFIXES)`. The parentheses do **not** form a single-element tuple — they evaluate to the bare value. `DEFAULT_TRUSTED_SB3_REPO_PREFIXES` is currently a tuple, so it is safe today, but anyone retyping the constant as a list ships a mutable default shared across calls. **Why it matters:** classic Python footgun, silently breaks isolation between sessions. **Fix:** use `None` sentinel and resolve inside the body, or annotate `Sequence[str]` with `tuple(DEFAULT_TRUSTED_SB3_REPO_PREFIXES)` as the default and add a typing test.

2. **(H) Polling-with-sleep paused loop.** `env_task` at [docugym/runtime.py](../docugym/runtime.py#L373-L375) does `if paused: await asyncio.sleep(0.01); continue`. Wakes the loop ~100×/s while paused, fights the display task's own polling, and adds latency to unpause. **Fix:** introduce `pause_event = asyncio.Event()` (set when not paused). Tasks `await pause_event.wait()`; `display_task` clears/sets it on toggle. Same pattern eliminates the paused render-loop in `wrapper.py::_hold_if_paused`.

3. **(H) Three duplicated `wait_for(q.get(), timeout=0.1)` polling loops.** `keyframe_task` [docugym/runtime.py](../docugym/runtime.py#L469-L475), `narrator_task` [docugym/runtime.py](../docugym/runtime.py#L521-L526), `tts_task` [docugym/runtime.py](../docugym/runtime.py#L583-L587). Each consumer sleeps on a 100 ms timer. **Why it matters:** drains battery on idle, adds up to 100 ms shutdown latency per task, and is the documented `asyncio` anti-pattern. **Fix:** use a sentinel (push `None` on `stop_event`) or `asyncio.wait({queue.get(), stop_event.wait()}, return_when=FIRST_COMPLETED)`. Python 3.11's `asyncio.timeout()` context manager would also clean these up if the polling shape is kept.

4. **(H) Two queues per frame, two dataclass allocations per frame.** [docugym/runtime.py](../docugym/runtime.py#L434-L441) emits both `_FrameEvent` and `_DisplayEvent` for every render. At 60 FPS this is ~120 dataclass allocations/s plus two queue ops. **Why it matters:** GC pressure on a hot path that is supposed to be the fast leg. **Fix:** emit one event consumed by both `keyframe_task` and `display_task` via fan-out (asyncio broadcast pattern), or use a shared latest-frame slot updated in place + `asyncio.Event.set()` to wake consumers.

5. **(H) Frame buffer aliasing across queues.** `env.render()` returns the env's internal RGB buffer for many Gymnasium envs; the same `frame` ndarray is pushed to `frame_q` (keyframe diffing), `display_q` (blit), and ultimately the recorder. The next `env.step()` may mutate it in place. **Why it matters:** sporadic display/keyframe-delta artefacts that are hard to attribute. **Fix:** `frame = np.ascontiguousarray(frame)` then `frame.flags.writeable = False` once at the boundary in `env_task`; document the immutability contract in the `_FrameEvent` dataclass docstring.

6. **(H) `subtitle_q` race between `narrator_task` and `tts_task`.** `narrator_task` writes the full narration to `subtitle_q` ([docugym/runtime.py](../docugym/runtime.py#L555)); `tts_task` writes per-sentence `graphemes` ([docugym/runtime.py](../docugym/runtime.py#L601-L602)). They overwrite each other depending on scheduling. **Why it matters:** subtitle flicker, occasional reversion to whole-paragraph subtitle mid-speech. **Fix:** have `narrator_task` only post a "pre-speech" subtitle when TTS is disabled; in voice mode, let `tts_task` own subtitle updates exclusively. Alternatively, give each writer a priority lane and let display drain in priority order.

7. **(H) Recorder writes inline before audio enqueue.** [docugym/runtime.py](../docugym/runtime.py#L610-L624) calls `active_recorder.write_audio_chunk(...)` then `active_audio_output.enqueue(chunk)`. If the ffmpeg audio sink (a file write here, but a pipe in the video path) blocks, audio playback enqueueing is delayed. The video path has the real risk: `_finalize_video_encoder` reads from the ffmpeg stderr pipe at close time, but `write_video_frame` writes to stdin without draining stderr — a long-running session can deadlock if stderr fills (default `subprocess.PIPE` is 64 KB on Linux). **Why it matters:** classic subprocess pipe-fill deadlock. **Fix:** in `recording.py::_start_video_encoder` either drop stderr to `subprocess.DEVNULL` and surface failure via the return code, or spawn a small drain thread that reads stderr into a bounded buffer.

8. **(H) `display_task` does not pace to `fps`.** Final `await asyncio.sleep(0)` ([docugym/runtime.py](../docugym/runtime.py#L705)) yields once per iteration; pacing is left to `Display._clock.tick(fps)` inside `blit_frame`. That works, but `pygame.time.Clock.tick` is a *blocking* call inside the asyncio loop — it sleeps the entire event loop. **Why it matters:** for the duration of the FPS sleep, no other coroutine (TTS, narrator, env) progresses. With 60 FPS that's up to ~16 ms blocked per tick. **Fix:** replace `Clock.tick` with a non-blocking deadline (`next_deadline += 1/fps`; `await asyncio.sleep(max(0, next_deadline - perf_counter()))`), or move the display onto a dedicated thread driven by an `asyncio.Queue` for frames and a `threading.Event` for shutdown. Note: this is a more impactful follow-up than item 3.

9. **(H) `latency_samples_ms` grows unbounded.** [docugym/runtime.py](../docugym/runtime.py#L353), appended every narration. Long sessions accumulate megabytes; percentiles blur regressions. **Fix:** `collections.deque(maxlen=...)` (e.g. last 256 samples) or an HDR histogram. Compute final percentiles via `numpy.percentile`/`statistics.quantiles` once.

10. **(M) `_percentile` re-sorts on every call and is invoked twice over the same list.** [docugym/runtime.py](../docugym/runtime.py#L155-L170) and end-of-run usage at [docugym/runtime.py](../docugym/runtime.py#L771-L772). Sort once or replace with `numpy.percentile`. Negligible CPU but trivially fixable.

11. **(M) Unused semaphores.** `narration_sem = asyncio.Semaphore(1)` and `tts_sem = asyncio.Semaphore(1)` ([docugym/runtime.py](../docugym/runtime.py#L354-L355)) are only acquired inside their single owning task. **Why it matters:** misleading code — implies concurrency control that does not exist. **Fix:** delete; if a future second consumer is added, re-introduce with documentation.

12. **(M) Reflection on the hot path.** `_set_display_flag` and `_clear_audio_buffer` ([docugym/runtime.py](../docugym/runtime.py#L172-L180)) use `getattr` + `callable` per call; called every action toggle and per frame state sync. **Fix:** since `Display` always implements these methods, call them directly; if the indirection exists for tests, define a Protocol and bind once at startup.

13. **(M) `isinstance` against `@runtime_checkable` Protocol per-call.** `_narrate_async` and `_speak_async` ([docugym/runtime.py](../docugym/runtime.py#L183-L217)) test the narrator/speaker every invocation. Protocol structural checks scan attributes — not free. **Fix:** resolve dispatch once before the consumer loop and store a bound coroutine factory.

14. **(M) Broad `except Exception` swallowing.** Multiple sites: VLM error ([docugym/runtime.py](../docugym/runtime.py#L540-L546)), recorder writes ([docugym/runtime.py](../docugym/runtime.py#L614-L622), [docugym/runtime.py](../docugym/runtime.py#L651-L657)), recorder finalize ([docugym/runtime.py](../docugym/runtime.py#L736-L739)), policy predict ([docugym/runtime.py](../docugym/runtime.py#L383-L392)). All log a one-line warning without `exc_info=True`, several silently disable subsystems. **Why it matters:** field debugging is harder; CI/RunResult appears successful even when recording silently failed. **Fix:** narrow except clauses, always pass `exc_info=True`, surface terminal subsystem failures on `RunResult` with explicit fields (`recording_failed: bool`, `narration_failures: int`).

15. **(M) `dropped_narration_candidates` counts two distinct conditions.** Incremented for `narration_q` overflow ([docugym/runtime.py](../docugym/runtime.py#L497)) and `tts_q` overflow ([docugym/runtime.py](../docugym/runtime.py#L559)). **Fix:** split into `dropped_keyframe_candidates` and `dropped_tts_inputs` on `RunResult`.

16. **(M) `on_narration` invoked synchronously inside the loop.** [docugym/runtime.py](../docugym/runtime.py#L573-L574) — user-supplied callback can block the event loop. **Fix:** wrap with `asyncio.to_thread` or document a non-blocking contract; mirror what `wrapper.py::_safe_callback` does.

17. **(M) `asyncio.gather(*tasks)` without aggregation.** [docugym/runtime.py](../docugym/runtime.py#L721) — the first failing task cancels the rest and only its exception surfaces; subsequent tracebacks are lost. **Fix:** use `asyncio.TaskGroup` (Python 3.11+; pyproject already targets 3.11). It propagates an `ExceptionGroup` aggregating all task failures and handles cancellation cleanly.

18. **(M) Cleanup ordering biases recorded duration.** [docugym/runtime.py](../docugym/runtime.py#L730-L739) — `audio_output.stop()` runs first, then `recorder.close(end_timestamp=perf_counter())`. The captured timestamp includes audio-stop overhead. **Fix:** capture `end_ts = perf_counter()` once at the top of the `finally` block and reuse it for both stops.

19. **(L) 35 keyword-only parameters on `run_session`.** [docugym/runtime.py](../docugym/runtime.py#L236-L272). **Fix:** group into dataclass configs (`SessionConfig`, `TTSConfig`, `RecordingConfig`) and have `run_session_sync` use `Unpack` (PEP 692) or accept the dataclass to keep static typing.

20. **(L) `run_session_sync(**kwargs: Any)`.** [docugym/runtime.py](../docugym/runtime.py#L760-L770) — loses static typing of the 35 parameters. Same fix as 19.

### docugym/wrapper.py

21. **(H) Per-frame `np.array(frame, copy=True)` in `_enqueue_narration`.** [docugym/wrapper.py](../docugym/wrapper.py#L539-L548) deep-copies the frame on every narration candidate (and again in `_save_clip`). With 210×160×3 Atari this is ~100 KB; with CarRacing's 96×96×3 it's tiny — but copy cost compounds when narration triggers fire. **Fix:** copy lazily — only when the worker thread actually starts processing the request. The producer can hand off a borrowed reference plus a `step_id` and the worker grabs the cached frame from a shared latest-frame slot if it has not been overwritten.

22. **(H) Busy-render loop while paused.** [docugym/wrapper.py](../docugym/wrapper.py#L498-L505) — `_hold_if_paused` calls `_render_current_frame` and `_handle_actions` in a tight `while paused` loop. The display's `Clock.tick(fps)` paces it to ~60 FPS, but it still re-blits the same frame and runs the entire status update + callbacks. **Why it matters:** wastes the GIL while paused; user callbacks fire 60×/s. **Fix:** use a `threading.Event` `unpaused` and `unpaused.wait()` to block; render once on transition.

23. **(M) Subtitle `queue.Queue(maxsize=8)` with drain-latest.** [docugym/wrapper.py](../docugym/wrapper.py#L172) — only the latest is read each tick (`drain_latest_sync`), so up to 7 stale entries are silently dropped. **Fix:** `maxsize=1` and accept that overwrites drop the oldest (already the intent of `push_drop_oldest_sync`).

24. **(M) Closures over loop variables in callbacks.** [docugym/wrapper.py](../docugym/wrapper.py#L332-L338), [docugym/wrapper.py](../docugym/wrapper.py#L382-L386) capture `chunk`/`text` via lambda. Today this works because `_safe_callback` is called immediately, but the pattern is fragile. **Fix:** use `functools.partial` or pass arguments explicitly (`callback=lambda c=chunk: self._on_audio_chunk(c)` is the standard idiom if a lambda is kept).

25. **(M) `_record_narration_result` mutates state under lock then calls `_push_subtitle` outside.** [docugym/wrapper.py](../docugym/wrapper.py#L364-L373) — `_latest_narration` is updated inside `_stats_lock`, but `_push_subtitle` re-acquires the lock to update `_latest_subtitle`. **Why it matters:** observers reading via `state()` between the two updates see narration without matching subtitle. **Fix:** atomically update both fields in one critical section.

26. **(M) Worker uses `narrate_frame_sync` but already runs on a background thread.** [docugym/wrapper.py](../docugym/wrapper.py#L302-L307) — wrapper spawns a `threading.Thread` and inside it calls the *sync* narrator (which under the hood `asyncio.run`s a coroutine). Each call therefore spins up and tears down a fresh event loop. **Why it matters:** ~1–5 ms per call of avoidable overhead; worse, the new loop creates a new `httpx.AsyncClient`, defeating connection pooling (see also finding 32). **Fix:** keep the worker async (`asyncio.new_event_loop()` once, reuse) or switch to the async `narrate_frame` and a single long-lived loop in the worker.

### docugym/display.py

27. **(H) `pygame.surfarray.make_surface` allocates per frame.** [docugym/display.py](../docugym/display.py#L156-L160) creates a new surface from `np.transpose` on every blit. Combined with `pygame.transform.scale` (also allocating). **Why it matters:** at 60 FPS this is a steady allocation cadence on Atari frames. **Fix:** keep one persistent `pygame.Surface` matched to the unscaled frame size and one for the scaled output; copy pixels via `pygame.surfarray.blit_array` (in-place) into the cached source surface, then `pygame.transform.scale` into the cached destination. Saves both allocations and the `np.transpose` materialisation by using `pygame.surfarray.pixels3d` reinterpretation.

28. **(H) `np.transpose(normalized_frame, (1, 0, 2))` materialises a non-contiguous copy on render.** [docugym/display.py](../docugym/display.py#L156). Fine for tiny frames; on 1920×1080 envs it stings. **Fix:** `pygame.surfarray.make_surface` accepts WxHx3 because pygame surfaces are column-major; an alternative is `pygame.image.frombuffer(frame.tobytes(), (w, h), 'RGB')` which avoids the transpose entirely. Benchmark before committing — both pygame paths are fiddly.

29. **(M) `_wrap_text` calls `font.size(...)` once per word for every render.** [docugym/display.py](../docugym/display.py#L437-L466). `Font.size` is not free; subtitle rendering happens every frame. **Fix:** memoise wrap output per `(text, max_width, font_height)` tuple — subtitle text changes far less than 60 Hz.

30. **(M) `font.render` of HUD text every frame.** [docugym/display.py](../docugym/display.py#L186-L188) renders the HUD string on every blit even when it has not changed. Same for subtitle lines. **Fix:** cache the rendered surface keyed by the text; invalidate on `set_status`/`set_subtitle`.

31. **(L) `pygame.init()` and `pygame.font.init()` in `Display.__init__`.** [docugym/display.py](../docugym/display.py#L66-L67) — making a second `Display` in the same process re-inits SDL (idempotent, but noisy). Not a real bug; a top-level module init guard would be cleaner.

### docugym/narrator.py

32. **(H) `httpx.AsyncClient` created and torn down per call.** [docugym/narrator.py](../docugym/narrator.py#L83-L91) opens a fresh `AsyncClient` for every narration request. **Why it matters:** TLS handshake cost (negligible for localhost), connection-pool warmup, HTTP/2 stream-id reset — measurable when narration cadence is sub-second. **Fix:** hold one `httpx.AsyncClient` on `VLMNarrator` instance; close in an `aclose()` method called from `run_session`'s `finally`.

33. **(H) PNG re-encode per narration.** [docugym/narrator.py](../docugym/narrator.py#L201-L210) — `Image.save(buffer, format="PNG")` then base64. PNG compression of a 384-px frame takes a few ms; JPEG is faster and produces smaller payloads (the VLM accepts JPEG via `data:image/jpeg`). **Fix:** switch to JPEG (quality ≈ 85) for `image_detail == "low"`, retain PNG only when lossless is required. Move the encode to `asyncio.to_thread` so the event loop is not blocked.

34. **(H) `_encode_image_payload` blocks the event loop.** PIL operations and base64 are CPU-bound and synchronous; `narrate_frame` is `async` but spends meaningful time in encoding before the `await client.post`. **Fix:** wrap the encode body in `asyncio.to_thread`; encoding can also be done concurrently with prior network ops if a request pipeline is built.

35. **(M) `wait_until_ready` swallows non-HTTP errors silently.** [docugym/narrator.py](../docugym/narrator.py#L131-L137) — `except httpx.HTTPError: pass`. If `base_url` is malformed (`InvalidURL`) the error is *not* `httpx.HTTPError` and propagates; if DNS hangs past `_timeout_seconds` we re-loop with an extra timeout per iteration. **Fix:** catch `httpx.RequestError` (broader, still excludes programmer errors) and validate `base_url` once in `__init__`.

36. **(M) No upper bound on `max_tokens` server response time.** `_timeout_seconds` defaults to 30 s and is reused for both readiness polling and chat completion. Long generations on a cold model can exceed it; readiness polling does not need 30 s. **Fix:** separate `request_timeout_seconds` and `readiness_request_timeout_seconds`.

37. **(L) The system prompt embeds raw newlines from the source string.** [docugym/narrator.py](../docugym/narrator.py#L14-L29) — `"""..."""` triple-quoted, leading whitespace on continuation lines. The model sees ragged whitespace. **Fix:** `textwrap.dedent` or store the prompt as a single line and rely on the model's tolerance, or store in a `prompts/` data file.

### docugym/audio.py

38. **(M) Drop-oldest implementation has a triple-try ladder.** [docugym/audio.py](../docugym/audio.py#L97-L114). The same pattern is exposed cleaner in `queue_utils.push_drop_oldest_sync`. **Fix:** delegate to the shared helper.

39. **(M) `_callback` is a Python callback inside a C audio thread.** Each iteration does `self._queue.get_nowait()`, which acquires the GIL. Under stress this can underrun. **Fix:** for low-latency, prefer `numpy.frombuffer` + ring buffer (`numpy` array of fixed size + atomic indices). Out of scope for now, but worth noting.

40. **(L) `latency: str = "low"`.** PortAudio accepts a numeric latency in seconds *or* `"low"`/`"high"`. Documentation should clarify which is used by default and surface a way to set numeric latency for users on tricky hardware.

### docugym/tts.py

41. **(M) `re.split` on every `_split_sentences` call.** [docugym/tts.py](../docugym/tts.py#L11), [docugym/tts.py](../docugym/tts.py#L113-L121). The compile happens once at module load (good) but `_SENTENCE_BOUNDARY_RE` only catches `. ! ?`-followed-by-whitespace; "Mr." style false positives exist. **Fix:** acceptable for this domain (Attenborough sentences) but document and add a unit test for "Mr. Pangolin runs." → 1 sentence.

42. **(M) `_chunk_audio` always slices full-length copies via list comprehension.** [docugym/tts.py](../docugym/tts.py#L139-L145). Each slice is a view, not a copy — actually fine — but the resulting list of views holds the full audio array alive. **Fix:** if memory matters during long sessions, materialise each chunk with `audio[start:end].copy()` so the source can be freed. Trade-off: memory vs. CPU; current behaviour is reasonable.

### docugym/recording.py

43. **(H) ffmpeg stderr pipe can deadlock the encoder.** [docugym/recording.py](../docugym/recording.py#L162-L170) — `stderr=subprocess.PIPE` is filled by ffmpeg progress logs but never drained until `_finalize_video_encoder` calls `process.communicate()`. With `loglevel=error` the volume is small, but `libx264 -preset ultrafast` will emit warnings on some inputs (e.g., odd frame heights). **Fix:** either `stderr=subprocess.DEVNULL` (lose the diagnostic) or spawn a drainer thread that captures stderr into a bounded `deque` for inclusion in the failure message.

44. **(M) Audio path mixes monotonic timestamp from `perf_counter()` of *write time*, not *playback time*.** `write_audio_chunk` uses the timestamp at which the runtime decided to call it ([docugym/runtime.py](../docugym/runtime.py#L617-L620)). For sample-accurate A/V sync, the recorder should accumulate samples written and derive offsets from `samples_written / sample_rate`. **Fix:** drop the `timestamp` parameter; `_write_silence` is computed from frame_count vs samples_written internally already.

45. **(M) `tobytes()` allocates per-frame.** `frame_rgb.tobytes()` ([docugym/recording.py](../docugym/recording.py#L83)) materialises a fresh bytes object every frame. **Fix:** use `self._video_process.stdin.write(memoryview(frame_rgb))` if the array is C-contiguous (it is, after `_normalize_frame`).

46. **(M) `_write_silence` allocates a 4 KB zeros block then loops.** [docugym/recording.py](../docugym/recording.py#L213-L223). Hoist to module-level constant or instance attribute to avoid per-call allocation.

### docugym/env.py

47. **(M) `load_sb3_policy` device hardcoded to CPU.** [docugym/env.py](../docugym/env.py#L146) — `loader.load(str(model_path), device="cpu")`. Project targets a 24 GB CUDA box; CPU inference is slow for larger Atari networks. **Fix:** pass device through from config (`agent.device: "cuda" | "cpu" | "auto"`).

48. **(M) `_load_policy_from_path` infers algorithm from filename prefix.** [docugym/env.py](../docugym/env.py#L113-L141). `ppo-PongNoFrameskip-v4.zip` → PPO. Brittle: any repo using a different naming pattern fails. **Fix:** accept explicit `algorithm` kwarg, fall back to filename inference. Worth pairing with a "trusted manifest" if the project widens beyond `sb3/` repos.

49. **(L) `_save_frame_png` imported lazily.** Fine, but `clips.py::_save_frame_png` duplicates the same helper. **Fix:** consolidate into `clips.py` (or a new `image_io.py`) and import from there.

### docugym/keyframes.py

50. **(M) `mean_abs_pixel_delta` does float32 cast of full frame.** [docugym/keyframes.py](../docugym/keyframes.py#L101-L104). For 1920×1080 frames at 60 FPS that is 6 MB/frame allocated. **Fix:** compare on a downsampled view (`frame[::4, ::4, :3]`) — the pixel-delta heuristic does not need full resolution. Project spec already mentions optical-flow as the alternative if the cheap version is noisy; the cheaper-still version is the right starting point.

51. **(M) `KeyframeSelector` retains a reference to the previous frame ndarray.** [docugym/keyframes.py](../docugym/keyframes.py#L87) — `self._previous_frame = frame`. Combined with finding 5, this can mean the "previous frame" was overwritten by env between calls, making the diff meaningless. **Fix:** the producer must hand the selector an immutable copy; pair with finding 5's writeable=False contract.

### docugym/queue_utils.py

52. **(L) `drain_latest_sync` and `drain_latest_async` are textually identical except for the queue type.** Acceptable duplication for typing reasons. No action required, noted for completeness.

### docugym/config.py

53. **(M) `load_settings` creates a dynamic subclass per call.** [docugym/config.py](../docugym/config.py#L138-L147) defines `SettingsWithYaml(AppSettings)` inside the function. For one-shot CLI use this is fine, but in tests that call `load_settings` repeatedly each call leaks a fresh class object. **Fix:** parameterise the YAML path through an `init_settings` source (Pydantic supports passing a path to `YamlConfigSettingsSource` from runtime), or use `model_config = SettingsConfigDict(yaml_file=...)` overridden via constructor.

54. **(L) `XTTSSettings` references a relative path default.** [docugym/config.py](../docugym/config.py#L67-L70) — `"data/voices/british_narrator.wav"` is relative to CWD. **Fix:** resolve against a configurable data dir or document the expectation.

### docugym/cli.py

55. **(M) Configuration flag duplication between `display-smoketest` and `run`.** [docugym/cli.py](../docugym/cli.py#L249-L321) and [docugym/cli.py](../docugym/cli.py#L350-L460) share ~12 identical Typer options. **Fix:** Typer supports option groups via callbacks or a typed dataclass shared between commands; alternative is `typer-config` or a small `_common_display_options()` helper that returns a `tuple[Option, ...]` (Typer's syntax makes this awkward; pragmatic fix is a small dataclass + manual passthrough).

56. **(M) `run` infers SB3 filename from policy shorthand by string concat.** [docugym/cli.py](../docugym/cli.py#L499-L502) — `f"{policy.rsplit('/', maxsplit=1)[-1]}.zip"`. Works for `sb3/ppo-Pong...` repos where the convention holds; breaks otherwise. **Fix:** require explicit `--filename` when `--policy` does not match a known pattern, or introduce a small lookup table in `env.py`.

57. **(L) `tune_prompt` divides by `len(results)` without checking emptiness.** [docugym/cli.py](../docugym/cli.py#L725) — only safe because `samples >= 1` and `run_prompt_tuning` guarantees `samples` results. Add an assertion or guard for clarity.

### docugym/clips.py

58. **(L) Microsecond-suffix on UTC timestamp.** [docugym/clips.py](../docugym/clips.py#L31) — `%Y%m%d-%H%M%S-%f`. Two saves within the same microsecond collide (rare but possible under rapid `s` keypress). **Fix:** add a short random suffix or a process-local incrementing counter.

### docugym/tune.py

59. **(M) Duplicate `_humanize_env_id`.** [docugym/tune.py](../docugym/tune.py#L29-L31) duplicates `narration_events.humanize_env_id`. **Fix:** import from `narration_events`.

### Cross-cutting

60. **(H) Two parallel orchestration paths.** `runtime.py` (async) and `wrapper.py` (sync threads) re-implement the same keyframe → narration → TTS → display pipeline with subtly different semantics (e.g., subtitle race, paused-loop policy, frame copy strategy). Each finding above must be cross-checked between both paths. **Why it matters:** double the bug surface; behaviour drift is already visible (wrapper deep-copies frames; runtime aliases). **Fix:** carve out a shared `Orchestrator` core whose I/O surfaces (frame source, action sink, narration sink, audio sink) are pluggable. Both `runtime.run_session` and `DocuWrapper.step` then become thin adapters. Track as `cdoc/`-level open task before more features land.

61. **(M) `Path.cwd()`-relative defaults.** `DEFAULT_CONFIG_PATH = Path("configs/default.yaml")` ([docugym/config.py](../docugym/config.py#L15)) and `out_dir=Path("out/clips")` ([docugym/clips.py](../docugym/clips.py#L26)) silently depend on the user's working directory. **Fix:** resolve against a project-root anchor or expose an env-var `DOCUGYM_DATA_DIR`.

62. **(M) `pyproject` Python version vs. type hints.** `from __future__ import annotations` is used pervasively (correct for forward refs), but `list[str] | tuple[str, ...]` style requires Python 3.10+. Pyproject declares 3.11 (per spec); good. Confirm `requires-python = ">=3.11"` in `pyproject.toml` to prevent users on 3.10 from installing a runtime that *imports* successfully but would fail at `isinstance(x, X | Y)` evaluation.

63. **(L) Logging at INFO is verbose on the hot path.** Multiple `logger.info(...)` per narration ([docugym/runtime.py](../docugym/runtime.py#L567-L572), [docugym/wrapper.py](../docugym/wrapper.py#L325-L330)). Consider DEBUG for body, keep INFO only for the count + step.

## Recommended next steps (not decisions — see related notes)

Triage in this order to maximise return:
1. Findings 7 / 43 (ffmpeg pipe deadlock — correctness risk)
2. Finding 60 (orchestration consolidation — multiplies every other fix)
3. Findings 8 / 27 / 28 / 32 / 33 (display + VLM hot paths)
4. Findings 5 / 51 (frame aliasing contract)
5. Findings 2 / 22 (pause-loop polling)
6. Remaining items as polish/refactor passes.

Each accepted item should land as its own short `decision` note (lightweight ADR) referencing this audit.

## Caveats

- Severities are reviewer judgement on a static read. None of the H-tagged items have been measured under load on the target hardware. Add benchmarks before allocating engineering time to fixes 27/28/32/33.
- Several "issues" (e.g., 11, 31, 52) are stylistic — explicitly tagged L. Do not block on them.
- The review did not exercise the test suite for behavioural verification; correctness claims (5, 6, 18, 25) should be reproduced with a targeted test before fix work.

## Changelog

- 2026-05-07: Created. Initial 63-finding inventory across 20 modules.
- 2026-05-07: Linked remediation-scope decision for accepted first-pass fixes
	and documented deferrals.
- 2026-05-11: Linked follow-up source-bloat remediation pass for additional
  local duplication, sync-helper, and display hot-path fixes.
