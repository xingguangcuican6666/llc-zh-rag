#!/usr/bin/env bash
# Launch the two local llama.cpp servers for the RAG translation pipeline.
#   BGE  (embeddings, CPU)  -> :18080
#   Qwen (generation, GPU)  -> :8080
#
# GPU rule: check `nvidia-smi` free VRAM FIRST.
#   game CLOSED  -> full/max offload (7B fits 8GB fully; 14B needs partial ~38 layers)
#   game RUNNING -> game holds ~2.7GB, drop NGL so llama.cpp does not OOM.
set -u
export LD_LIBRARY_PATH="${LLC_CUDA_LIB:-/opt/cuda/lib64}:${LD_LIBRARY_PATH:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# 每台机器的路径来自可选的 ../.llcenv（不入库），否则用 $HOME 兜底、LOG 放脚本旁
[ -f "$HERE/../.llcenv" ] && { set -a; . "$HERE/../.llcenv"; set +a; }
BIN="${LLC_LLAMA:-$HOME/zliu-runtime/llama.cpp/build-cuda/bin/llama-server}"   # CUDA-enabled build
MODELS="${LLC_MODELS:-$HOME/zliu-runtime/models}"
LOG="${LLC_LOG:-$HERE/logs}"
mkdir -p "$LOG"

QMODEL="${QMODEL:-14b}"    # which Qwen to serve: 7b | 14b
QCTX="${QCTX:-4096}"
case "$QMODEL" in
  7b)  QM="$MODELS/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf";  DEF_NGL=99 ;;  # 4.6GB, fits 8GB fully
  14b) QM="$MODELS/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"; DEF_NGL=38 ;;  # ~9GB, partial offload on 8GB
  *)   echo "unknown QMODEL=$QMODEL (use 7b|14b)"; exit 1 ;;
esac
NGL="${NGL:-$DEF_NGL}"     # override to lower when the game is holding VRAM

start_bge() {
  if curl -sf http://127.0.0.1:18080/health >/dev/null 2>&1; then echo "BGE already up"; return; fi
  nohup "$BIN" -m "$MODELS/bge-small-zh-v1.5-q8_0.gguf" \
    --embeddings --pooling cls -c 512 -ub 512 -b 512 --parallel 4 \
    -ngl 0 --host 127.0.0.1 --port 18080 \
    > "$LOG/bge.log" 2>&1 &
  echo "BGE pid $!"
}
start_qwen() {
  if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then echo "Qwen already up"; return; fi
  nohup "$BIN" -m "$QM" \
    -c "$QCTX" --parallel 1 -ngl "$NGL" --host 127.0.0.1 --port 8080 \
    > "$LOG/qwen.log" 2>&1 &
  echo "Qwen pid $! (model=$QMODEL ngl=$NGL ctx=$QCTX)"
}

case "${1:-both}" in
  bge)  start_bge ;;
  qwen) start_qwen ;;
  both) start_bge; start_qwen ;;
  # kill by model-path patterns (safe: only runs in this branch, never alongside a launch)
  stop) pkill -f 'llama-server .*bge-small'; pkill -f 'llama-server .*qwen2.5-[0-9]*b-instruct'; echo stopped ;;
esac
