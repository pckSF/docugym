#!/usr/bin/env bash
set -euo pipefail

MODEL="${DOCUGYM_VLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct-AWQ}"
PORT="${DOCUGYM_VLM_PORT:-8000}"
GPU_UTIL="${DOCUGYM_VLM_GPU_UTIL:-0.70}"
HOST="${DOCUGYM_VLM_HOST:-127.0.0.1}"

case "${HOST}" in
  127.*|::1|localhost)
    ;;
  *)
    if [[ "${DOCUGYM_VLM_ALLOW_PUBLIC:-}" != "1" ]]; then
      printf '%s\n' \
        "Refusing to bind vLLM to non-loopback host '${HOST}'." \
        "Set DOCUGYM_VLM_ALLOW_PUBLIC=1 only when the endpoint is protected by network controls." >&2
      exit 2
    fi
    printf '%s\n' \
      "Warning: binding unauthenticated vLLM endpoint to '${HOST}'." \
      "Use only on trusted networks or behind an authenticated proxy." >&2
    ;;
esac

exec vllm serve "${MODEL}" \
  --max-model-len 4096 \
  --limit-mm-per-prompt '{"image":1,"video":0}' \
  --gpu-memory-utilization "${GPU_UTIL}" \
  --mm-processor-cache-gb 0 \
  --dtype auto \
  --host "${HOST}" \
  --port "${PORT}"
