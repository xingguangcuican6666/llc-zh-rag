"""Held-out demo: translate confirmed pairs with their own line excluded from
retrieval, then compare RAG output to the community reference translation."""
import os, sys, json, re, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translate

random.seed(7)
META = [json.loads(l) for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index", "tm_meta.jsonl"), encoding="utf-8")]

def pick(n=12):
    # diverse, meaningful lines: has hangul, 6..60 chars, prefer story-ish
    cand = [m for m in META if re.search(r'[가-힣]', m["kr"]) and 6 <= len(m["kr"]) <= 60]
    random.shuffle(cand)
    return cand[:n]

def sim(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, len(sa | sb))

def main():
    sample = pick(12)
    exact = 0; sims = []
    for i, m in enumerate(sample, 1):
        out = translate.translate_unit({"kr": m["kr"], "en": m["en"]},
                                        k=8, exclude_self=True)
        ref = m["zh"]
        s = sim(out, ref); sims.append(s)
        if out == ref: exact += 1
        print(f"\n[{i}] @ {m['rel']}")
        print(f"  KR : {m['kr']}")
        if m["en"]: print(f"  EN : {m['en']}")
        print(f"  RAG: {out}")
        print(f"  REF: {ref}")
        print(f"  char-Jaccard={s:.2f}{'  EXACT' if out==ref else ''}")
    print(f"\n=== {len(sample)} held-out units | exact={exact} | mean char-Jaccard={sum(sims)/len(sims):.2f} ===")

if __name__ == "__main__":
    main()
