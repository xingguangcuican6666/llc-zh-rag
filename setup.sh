#!/usr/bin/env bash
# 从零重建 LLC 翻译流水线的运行环境。
# 仓库只含脚本；模型与游戏文本派生数据（索引/词表/快照）都在这里本地重建。
#
# 前置：已安装本地游戏（韩/英/官方文本）+ 已编译带 CUDA 的 llama.cpp。
# 用法：  bash setup.sh          # 全流程
#         bash setup.sh models   # 只下模型
#         bash setup.sh index    # 只重建词表+索引+快照（需游戏文本 & 服务）
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
RAG="$ROOT/rag"
MODELS="${LLC_MODELS:-$HOME/zliu-runtime/models}"
LLAMA="${LLC_LLAMA:-$HOME/zliu-runtime/llama.cpp/build-cuda/bin/llama-server}"
# 下载走代理（按需改；置空则直连）
PROXY="${LLC_PROXY:-http://127.0.0.1:7890}"
# GGUF 仓库（bartowski 的分片命名与本项目文件名一致；BGE 仓库请按需核对）
REPO_14B="${LLC_REPO_14B:-bartowski/Qwen2.5-14B-Instruct-GGUF}"
REPO_7B="${LLC_REPO_7B:-bartowski/Qwen2.5-7B-Instruct-GGUF}"
REPO_BGE="${LLC_REPO_BGE:-CompendiumLabs/bge-small-zh-v1.5-gguf}"

hfdl(){ # repo, glob-or-file
  local extra=""; [ -n "$PROXY" ] && extra="HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY"
  echo "  hf download $1  ($2)"
  env $extra hf download "$1" "$2" --local-dir "$MODELS" >/dev/null
}

deps(){
  echo "== 1. python 依赖 =="
  python3 -m pip install -q -r "$ROOT/requirements.txt" && echo "  ok"
}

models(){
  echo "== 2. 模型 (-> $MODELS) =="
  mkdir -p "$MODELS"
  command -v hf >/dev/null || { echo "  缺少 hf CLI: pip install -U huggingface_hub"; return 1; }
  [ -f "$MODELS/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf" ] \
    && echo "  14B 已存在，跳过" || hfdl "$REPO_14B" "*q4_k_m*.gguf"
  [ -f "$MODELS/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf" ] \
    && echo "  7B 已存在，跳过"  || hfdl "$REPO_7B"  "*q4_k_m*.gguf"
  [ -f "$MODELS/bge-small-zh-v1.5-q8_0.gguf" ] \
    && echo "  BGE 已存在，跳过" || hfdl "$REPO_BGE" "*q8_0.gguf"
}

check_llama(){
  echo "== 3. llama.cpp (CUDA) =="
  if [ -x "$LLAMA" ]; then echo "  已就绪: $LLAMA"; else
    cat <<TXT
  未找到 llama-server: $LLAMA
  需自行编译带 CUDA 的 llama.cpp（环境相关，setup 不代劳）：
    git clone https://github.com/ggml-org/llama.cpp \$HOME/zliu-runtime/llama.cpp
    cd \$HOME/zliu-runtime/llama.cpp
    cmake -B build-cuda -DGGML_CUDA=ON && cmake --build build-cuda --config Release -j --target llama-server
TXT
    return 1
  fi
}

index(){
  echo "== 4. 词表 + 翻译记忆索引 + 基线快照 =="
  # BGE 需在线（build_tm 要嵌入）；用 llc 拉起服务
  "$ROOT/llc" up 14b || { echo "  服务未起来，先修好 llc up 再重跑 setup.sh index"; return 1; }
  echo "  -- build_glossary.py（挖词表 -> glossary_locked.json）"
  ( cd "$RAG" && python3 build_glossary.py )
  echo "  -- build_tm.py（嵌入平行语料 -> index/，约 10 万对，CPU 数分钟）"
  ( cd "$RAG" && python3 build_tm.py )
  echo "  -- incremental.py snapshot（记录官方文本基线）"
  ( cd "$RAG" && python3 incremental.py snapshot )
}

case "${1:-all}" in
  models) models ;;
  index)  index ;;
  deps)   deps ;;
  all)    deps; models; check_llama && index
          echo "== 完成。 试试:  llc status  =="  ;;
  *) echo "用法: bash setup.sh [all|deps|models|index]"; exit 1 ;;
esac
