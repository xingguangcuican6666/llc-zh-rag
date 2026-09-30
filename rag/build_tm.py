"""Build the translation-memory index from every confirmed KR<->zh pair in the mod.

For each zh file under Lang/LLC_zh-CN that has EN+KR official counterparts, align
KR/EN/zh with align.aligned_pairs (path-aligned when the zh structure matches the
official EN, id-aligned for the ~38 files whose dataList drifted) and collect clean
(kr, en, zh) triples. Embed the source side (KR, falling back to EN) with BGE and
save vectors + metadata for RAG retrieval.
"""
import os, sys, json, glob, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm, align

os.chdir(common.localize_dir())
ZH_ROOT = "../../../Lang/LLC_zh-CN"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index")
os.makedirs(OUT_DIR, exist_ok=True)

def collect():
    pairs = []
    seen = set()
    zh_files = glob.glob(f"{ZH_ROOT}/**/*.json", recursive=True)
    n_files = 0
    for zp in sorted(zh_files):
        rel = os.path.relpath(zp, ZH_ROOT)
        aligned = align.aligned_pairs(rel)
        if not aligned:
            continue
        n_files += 1
        for kr, en, zh in aligned:
            zh = (zh or "").strip()
            en = (en or "").strip()
            kr = (kr or "").strip()
            src = kr or en
            if not zh or not src:
                continue
            if zh == kr:                               # verbatim passthrough (codes/tuples), not a translation
                continue
            if zh == en and common.is_symbolic(en):    # symbol-only, no signal
                continue
            if zh == en and not kr:                     # untranslated & no KR to learn from
                continue
            key = (src, zh)
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"kr": kr, "en": en, "zh": zh, "rel": rel})
    return pairs, n_files

def main():
    pairs, n_files = collect()
    print(f"files scanned with EN+KR+zh: {n_files}")
    print(f"unique parallel pairs: {len(pairs)}")
    srcs = [(p["kr"] or p["en"]) for p in pairs]
    print("embedding source side with BGE ...")
    vecs = np.asarray(llm.embed(srcs, batch=64), dtype=np.float32)
    # normalize for cosine via dot product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs /= norms
    np.save(f"{OUT_DIR}/tm_vecs.npy", vecs)
    with open(f"{OUT_DIR}/tm_meta.jsonl", "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"saved {vecs.shape} -> {OUT_DIR}/tm_vecs.npy  +  tm_meta.jsonl")

if __name__ == "__main__":
    main()
