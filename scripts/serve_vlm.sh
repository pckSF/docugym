#!/usr/bin/env bash
set -euo pipefail

MODEL="${DOCUGYM_VLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct-AWQ}"
PORT="${DOCUGYM_VLM_PORT:-8000}"
GPU_UTIL="${DOCUGYM_VLM_GPU_UTIL:-0.70}"

exec vllm serve "${MODEL}" \
  --max-model-len 4096 \
  --limit-mm-per-prompt '{"image":1,"video":0}' \
  --gpu-memory-utilization "${GPU_UTIL}" \
  --mm-processor-cache-gb 0 \
  --dtype auto \
  --port "${PORT}"
