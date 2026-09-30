"""RAG translator: retrieve similar confirmed pairs + glossary, prompt Qwen."""
import os, sys, json, re, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm

IDX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index")
GLOSS_LOCKED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary_locked.json")

_vecs = None; _meta = None; _gloss = None

def _load():
    global _vecs, _meta, _gloss
    if _vecs is None:
        _vecs = np.load(f"{IDX}/tm_vecs.npy")
        _meta = [json.loads(l) for l in open(f"{IDX}/tm_meta.jsonl", encoding="utf-8")]
        _gloss = json.load(open(GLOSS_LOCKED, encoding="utf-8")) if os.path.exists(GLOSS_LOCKED) else {}

def retrieve(src, k=8, exclude_src=None):
    _load()
    q = np.asarray(llm.embed([src])[0], dtype=np.float32)
    q /= (np.linalg.norm(q) or 1.0)
    sims = _vecs @ q
    idx = np.argpartition(-sims, min(k*4, len(sims)-1))[:k*4]
    idx = idx[np.argsort(-sims[idx])]
    out, seen = [], set()
    for i in idx:
        m = _meta[i]
        if exclude_src is not None and (m["kr"] or m["en"]) == exclude_src:
            continue                   # held-out: don't leak the answer for this exact line
        key = m["zh"]
        if key in seen:                # dedup identical target
            continue
        seen.add(key)
        out.append((float(sims[i]), m))
        if len(out) >= k:
            break
    return out

HANGUL = re.compile(r'[가-힣]')
# short user-confirmed proper nouns that must inject even below the length gate
SHORT_SAFE = {"뿌이", "세븐", "시본"}
MAX_INJECT = 15

def glossary_hits(unit):
    """Locked term mappings to force for this unit — precise, longest-match-first.

    Injecting a wrong lock hurts prose (e.g. 이상 'or more' -> 李箱), so:
      - exact whole-value source match always injects (it's a name/label unit);
      - KR substring match only for distinctive keys (len>=3, or SHORT_SAFE),
        which excludes 1-2 char homographs like 이상/나/뇌/기사;
      - EN substring match only for multi-word keys (drops generic words like
        All/Face/Free); single-word EN injects only on exact match;
      - a key contained in a longer matched key is dropped; capped at MAX_INJECT.
    """
    _load()
    kr = (unit.get("kr", "") or "").strip()
    en = (unit.get("en", "") or "").strip()
    matched = []
    for term, zh in _gloss.items():
        if not term:
            continue
        is_kr = bool(HANGUL.search(term))
        if term == kr or term == en:                 # whole-value unit -> always safe
            matched.append((term, zh)); continue
        if is_kr:
            if (len(term) >= 3 or term in SHORT_SAFE) and kr and term in kr:
                matched.append((term, zh))
        else:                                          # EN key: only multi-word substrings
            if " " in term and en and term in en:
                matched.append((term, zh))
    # longest source first; drop any key that is a substring of a longer matched key
    matched.sort(key=lambda t: len(t[0]), reverse=True)
    hits, kept = {}, []
    for term, zh in matched:
        if any(term in k for k in kept):
            continue
        kept.append(term); hits[term] = zh
        if len(hits) >= MAX_INJECT:
            break
    return hits

SYS = (
    "你是《边狱公司》(Limbus Company) 的专业本地化译者。"
    "把韩语(权威原文)翻译成简体中文，英文仅作辅助参考。"
    "严格遵守：\n"
    "1. 保留所有 TextMeshPro 富文本标签(如 <color=#…> <b> <i> <size> </color>)原样不动。\n"
    "2. 保留形如 [SuperCoin] 的引擎关键字代码与形如 {0} {1} 的占位符，位置和数量不变。\n"
    "3. 保留换行(真实换行符)。\n"
    "4. 参照给出的对照译例，沿用其术语与语气风格。\n"
    "5. 译文必须是纯简体中文。除第 1、2 条要求原样保留的标签/代码/占位符外，"
    "不得出现任何英文单词或韩文；人名、地名、招式名等专有名词一律译成中文"
    "(参照固定译名与译例)。绝不允许中英混杂或原文照抄。\n"
    "6. 忠实原文，不增不减：只翻译原文写出的内容，不得添加原文没有的称呼、昵称、"
    "语气词、评论或解释，也不得漏译或改写原意。原文简短则译文也简短。\n"
    "7. 只输出译文正文，不要任何解释、引号或前后缀。"
)

# stray Latin/Hangul detector: what counts as leakage after removing the parts
# rule 1/2 says to keep verbatim ([EngineCodes], {N}, <tags>).
_KEEP = re.compile(r'\[[A-Za-z0-9_]+\]|\{[0-9]+\}|</?[^>]+>')
_LEAK = re.compile(r'[A-Za-z가-힣]')

def _leaks(text, en=""):
    """True if output has stray Latin/Hangul beyond preserved codes/tags.
    Latin words that also appear verbatim in the EN reference (legit loanwords the
    community keeps, e.g. 'R Corp.') are tolerated."""
    stripped = _KEEP.sub('', text)
    leftovers = re.findall(r'[A-Za-z]{2,}|[가-힣]+', stripped)
    if not leftovers:
        return False
    en_words = set(re.findall(r'[A-Za-z]{2,}', en))
    for w in leftovers:
        if re.search(r'[가-힣]', w):        # any leftover Hangul always leaks
            return True
        if w not in en_words:               # Latin word not sanctioned by the EN ref
            return True
    return False

CTX = 4096          # Qwen server context; prompt is budgeted to fit under it
EX_MAXLEN = 140     # cap each retrieved example side

def build_messages(unit, k=8, exclude_self=False):
    """Assemble system+user messages, budgeting the prompt to fit CTX.
    Returns (messages, out_tokens): output budget scales with source length and
    examples are trimmed/dropped so the total never exceeds the context window."""
    kr, en = unit.get("kr", "") or "", unit.get("en", "") or ""
    src = kr or en
    out_tokens = min(900, max(256, int(len(src) * 2)))
    # ~2.2 tokens/char worst case (KR/CJK); reserve output + system + safety
    input_char_budget = max(400, int((CTX - out_tokens - 220 - 64) / 2.2))
    hits = glossary_hits(unit)
    gloss = ("必须使用的固定译名：\n" +
             "\n".join(f"  {s} → {z}" for s, z in hits.items())) if hits else ""
    tgt = "待翻译：\n" + (f"  英文参考: {en}\n" if en else "") + \
          f"  韩文原文: {kr or en}\n只输出中文译文："
    ex_budget = max(0, input_char_budget - len(gloss) - len(tgt) - 20)
    ex = retrieve(src, k=k, exclude_src=(src if exclude_self else None))
    lines, used = [], 0
    for _, m in ex:                       # sorted by similarity desc; keep the best that fit
        s = (m["kr"] or m["en"])[:EX_MAXLEN]
        block = f"  原文: {s}\n  译文: {m['zh'][:EX_MAXLEN]}"
        if lines and used + len(block) > ex_budget:
            break
        lines.append(block); used += len(block)
    parts = []
    if gloss: parts.append(gloss)
    if lines: parts.append("对照译例(沿用其风格与术语)：\n" + "\n".join(lines))
    parts.append(tgt)
    return ([{"role": "system", "content": SYS},
             {"role": "user", "content": "\n\n".join(parts)}], out_tokens)

def clean(out):
    out = out.strip()
    # strip accidental wrapping quotes / leading labels
    out = re.sub(r'^(译文|中文译文|翻译)[:：]\s*', '', out)
    if len(out) >= 2 and out[0] in '「"“\'' and out[-1] in '」"”\'':
        out = out[1:-1].strip()
    return out

def translate_unit(unit, k=8, temperature=0.1, exclude_self=False, hq=True):
    """Translate one unit. With hq=True (default), if the output leaks stray
    Latin/Hangul (the dominant failure mode), retry greedily with an explicit
    correction turn; the cleaner of the two is returned. Set hq=False for the
    single-shot behaviour used in earlier benchmarks."""
    kr, en = unit.get("kr", "") or "", unit.get("en", "") or ""
    msgs, out_tokens = build_messages(unit, k=k, exclude_self=exclude_self)
    out = clean(llm.chat(msgs, temperature=temperature, max_tokens=out_tokens))
    if not hq or not _leaks(out, en):
        return out
    # retry: show the model its leaking draft and demand pure Chinese, greedy decode
    fix = msgs + [
        {"role": "assistant", "content": out},
        {"role": "user", "content":
            "上面的译文里混入了不该出现的英文或韩文。请重译，"
            "除标签/[代码]/{占位符}外必须是纯简体中文，专有名词也要译成中文。只输出译文："},
    ]
    out2 = clean(llm.chat(fix, temperature=0.0, max_tokens=out_tokens))
    # prefer the retry only if it actually stopped leaking (or the first still leaks)
    if not _leaks(out2, en):
        return out2
    return out if not _leaks(out, en) else out2

if __name__ == "__main__":
    u = {"kr": "관리자님, 잠시 시간 괜찮으신가요?", "en": "Manager, do you have a moment?"}
    print("EX retrieved:")
    for s, m in retrieve(u["kr"], 5):
        print(f"  {s:.3f}  {(m['kr'] or m['en'])[:40]} -> {m['zh'][:40]}")
    print("GLOSS:", glossary_hits(u))
    print("OUT:", translate_unit(u))
