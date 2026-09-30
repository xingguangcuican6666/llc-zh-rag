"""Batch quality test against the COMMUNITY translation as gold standard.

Sample N community-translated files (excluding the 104 I machine-translated),
draw a few real translated units from each, RAG-translate them with their own
reference held out of retrieval, and score vs the community zh:
  exact-match rate + char-level Jaccard (a lexical proxy; paraphrase scores low
  even when correct, so it is a floor on quality, not the ceiling).
"""
import os, sys, json, glob, re, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); import common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import align, translate

os.chdir(common.localize_dir())
ZH = "../../../Lang/LLC_zh-CN"
MINE = set(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mine_rels.json"))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_results.jsonl")
N_FILES = int(os.environ.get("N_FILES", "100"))
PER_FILE = int(os.environ.get("PER_FILE", "2"))

HAN = re.compile(r'[가-힣]')
random.seed(20260929)

def translated_units(rel):
    """Real KR->zh translation units (not codes/passthrough) from a community file."""
    out = []
    for kr, en, zh in align.aligned_pairs(rel):
        kr, en, zh = kr.strip(), en.strip(), zh.strip()
        if not kr or not zh or not HAN.search(kr):
            continue
        if zh == kr or zh == en or common.is_symbolic(kr) or len(kr) < 6:
            continue
        out.append({"kr": kr, "en": en, "zh": zh})
    return out

def sim(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, len(sa | sb))

def main():
    files = []
    for zp in sorted(glob.glob(f"{ZH}/**/*.json", recursive=True)):
        rel = os.path.relpath(zp, ZH)
        if rel in MINE:
            continue
        enp, krp, _, _ = common.variants(rel)
        if os.path.exists(enp) and os.path.exists(krp):
            files.append(rel)
    random.shuffle(files)
    picked, samples = 0, []
    for rel in files:
        if picked >= N_FILES:
            break
        units = translated_units(rel)
        if not units:
            continue
        random.shuffle(units)
        for u in units[:PER_FILE]:
            u["rel"] = rel
            samples.append(u)
        picked += 1
    print(f"community files sampled: {picked}  units: {len(samples)}", flush=True)
    exact, sims, errs = 0, [], 0
    fout = open(OUT, "w", encoding="utf-8")
    for i, u in enumerate(samples, 1):
        try:
            rag = translate.translate_unit({"kr": u["kr"], "en": u["en"]}, k=8, exclude_self=True)
        except Exception as e:
            errs += 1
            fout.write(json.dumps({"rel": u["rel"], "kr": u["kr"], "en": u["en"],
                                   "ref": u["zh"], "rag": None, "error": str(e)[:120]},
                                  ensure_ascii=False) + "\n"); fout.flush()
            continue
        s = sim(rag, u["zh"]); sims.append(s)
        ex = (rag == u["zh"]); exact += ex
        rec = {"rel": u["rel"], "kr": u["kr"], "en": u["en"], "ref": u["zh"], "rag": rag,
               "exact": ex, "jaccard": round(s, 3)}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
        if i % 20 == 0:
            print(f"  {i}/{len(samples)}  running exact={exact}  meanJ={sum(sims)/len(sims):.3f}  errs={errs}", flush=True)
    fout.close()
    n = len(sims); sims_sorted = sorted(sims)
    med = sims_sorted[n // 2] if n else 0
    ge = lambda t: sum(1 for x in sims if x >= t)
    print(f"\n=== {n} units scored ({errs} errors) | {picked} community files ===")
    print(f"exact match: {exact} ({100*exact/n:.1f}%)")
    print(f"char-Jaccard mean={sum(sims)/n:.3f} median={med:.3f}")
    print(f"  >=0.80: {ge(.8)} ({100*ge(.8)/n:.0f}%)   >=0.60: {ge(.6)} ({100*ge(.6)/n:.0f}%)   >=0.40: {ge(.4)} ({100*ge(.4)/n:.0f}%)   <0.20: {sum(1 for x in sims if x<.2)}")
    print(f"full results -> {OUT}")

if __name__ == "__main__":
    main()
