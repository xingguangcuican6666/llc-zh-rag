# LLC zh-CN 翻译流水线

《边狱公司 / Limbus Company》社区简体中文 Mod（`Lang/LLC_zh-CN/`）的本地化流水线：
以 **RAG（检索增强）+ 本地 LLM** 处理官方文本的周期性更新——用官方韩↔中平行语料做翻译记忆，
检索最相似的已确认译例 + 锁定术语词表，喂给本地 Qwen 生成，产出官方级、术语一致的译文。

全程在本机跑，无需联网（除首次下模型）：
- **BGE-small-zh**（嵌入，CPU）`:18080`
- **Qwen2.5-14B-Instruct-Q4_K_M**（生成，GPU，RTX 5060 8G 部分卸载）`:8080`

## 快速开始

```bash
git clone <this-repo> llc-rag && cd llc-rag
cp .llcenv.example .llcenv   # 按本机路径改：游戏目录 / 模型目录 / llama-server / 代理
bash setup.sh                # 装依赖、下模型、重建词表/索引/快照
ln -sf "$PWD/llc" ~/.local/bin/llc   # 可选：全局可用
llc status                   # 看显存 / 服务 / 基线 / 待翻译增量
```

前置：本机已安装游戏（含官方 en/kr 文本），并已编译带 CUDA 的 llama.cpp（见 `setup.sh` 提示）。

## 日常：官方更新后的周更流程

`llc` 是唯一入口（已软链到 `~/.local/bin/llc`）：

| 命令 | 作用 |
|------|------|
| `llc up [7b\|14b]` | 启动本地服务，**自动按当前空闲显存挑 NGL**（编码了 8G 显存规则） |
| `llc status` | 显存 / 两个服务健康 / 快照时间 / `plan` 增量 |
| `llc plan` | diff 官方文本，列出本次新增/改动的韩文单元 |
| `llc preview [N]` | 抽检 N 条增量机翻（不写文件，默认 8） |
| `llc run` | 翻译增量并写入 `Lang/LLC_zh-CN` |
| `llc verify` | 结构校验（`verify.py` 存在时） |
| `llc snapshot` | 确认无误后把当前官方文本记为新基线 |
| `llc down` | 安全停服（按端口，不用 pkill） |
| `llc week` | 打印完整 7 步流程 |

## 仓库不含什么，以及为什么

为控制体积、且**不重分发游戏文本/模型权重**，以下均由 `setup.sh` 在本地重建（见 `.gitignore`）：

- **模型权重**（`*.gguf`，~14G）—— `setup.sh models` 用 `hf` 下载（可走代理 `LLC_PROXY`）。
- **翻译记忆索引** `rag/index/`（247M，嵌入了游戏文本）—— `build_tm.py` 重建。
- **官方文本基线** `rag/snapshot.json` —— `llc snapshot` 重建。
- **派生词表** `glossary_locked.json` / `glossary.json` —— `build_glossary.py` 重建。
- 评测输出、日志、`mine_rels.json`（可按 mtime 重建）。

## 组件

| 文件 | 作用 |
|------|------|
| `llc` | 工作台入口（本文件表格里的所有命令） |
| `setup.sh` | 从零重建环境（deps / models / index） |
| `rag/serve.sh` | 拉起两个 llama.cpp 服务；`QMODEL=7b\|14b`、`NGL`、`QCTX` 可调 |
| `rag/translate.py` | RAG 译者：检索译例 + 锁定词表 → Qwen；含泄漏检测 + 重译 |
| `rag/incremental.py` | 增量流水线：diff 官方 KR vs 快照，只翻新增/改动（含 Hangul-gate 守卫） |
| `rag/build_tm.py` | 嵌入平行语料 → `index/`（翻译记忆） |
| `rag/build_glossary.py` | 挖掘并锁定术语 → `glossary_locked.json`（USER 词典优先） |
| `rag/align.py` | 官方 EN 结构对齐（drift 文件按 id/key 对齐） |
| `rag/llm.py` / `common.py` | 服务薄客户端 / 文本单元提取与规则 |

## 显存规则（RTX 5060, 8G）

`llc up` 会读 `nvidia-smi` 当前空闲显存自动挑 NGL：14B ≈ `(free-1800)/187` 层（上限 48），
7B 空闲≥6.2G 时整卡 `-ngl 99`。**游戏开着会占 ~2.7G**，此时自动降 NGL 以免 OOM；
换模型（7B↔14B）先 `llc down` 释放显存。

## 注意

- 无硬编码路径：脚本仓库位置由脚本自身位置推导；游戏目录/模型/llama-server 等
  机器相关路径全部走环境变量（`LLC_LOC` / `LLC_MODELS` / `LLC_LLAMA` / `LLC_PROXY`），
  由不入库的 `.llcenv`（见 `.llcenv.example`）提供；`LLC_LOC` 未设时还会从游戏目录自动探测。
- 只维护自己新翻的文件，不改社区已有译文。术语约定见词表与 `translate.py` 的 SYS 提示。
