"""Mine a high-precision KR->zh / EN->zh term glossary from the aligned corpus.

Whole-value short strings (teller names, skill/item/buff names, UI labels) are
1:1 term pairs. With raw frequencies we keep only terms whose dominant rendering
is consistent across the corpus. Merged with cleaned name data and the user's
authoritative corrections (which override everything).
"""
import os, sys, json, re, glob
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); import common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import align

os.chdir(common.localize_dir())
ZH = "../../../Lang/LLC_zh-CN"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary_locked.json")

HANGUL = re.compile(r'[가-힣]')
LATIN  = re.compile(r'[A-Za-z]')
CJK    = re.compile(r'[一-鿿]')
SENT   = re.compile(r'[.!?…。！？\n]')          # sentence punctuation -> not a term
BRK    = re.compile(r'[<>{}\[\]]')              # tags/placeholders -> skip as a term

MIN_COUNT = 3
MIN_RATIO = 0.66

def term_like(s, max_len):
    s = s.strip()
    return bool(s) and len(s) <= max_len and not SENT.search(s) and not BRK.search(s)

def mine():
    kr_map = defaultdict(Counter)   # KR term -> zh counts
    en_map = defaultdict(Counter)   # EN term -> zh counts
    files = 0
    for zp in sorted(glob.glob(f"{ZH}/**/*.json", recursive=True)):
        rel = os.path.relpath(zp, ZH)
        pairs = align.aligned_pairs(rel)
        if not pairs: continue
        files += 1
        for kr, en, zh in pairs:
            kr, en, zh = kr.strip(), en.strip(), zh.strip()
            if not zh or not CJK.search(zh) or not term_like(zh, 16):
                continue
            if HANGUL.search(kr) and term_like(kr, 14) and not LATIN.search(kr):
                kr_map[kr][zh] += 1
            # EN term: looks like a name/label, not prose
            if en and term_like(en, 24) and len(en.split()) <= 4 and not HANGUL.search(en):
                en_map[en][zh] += 1
    return kr_map, en_map, files

def consistent(counter_map):
    locked = {}
    for term, c in counter_map.items():
        total = sum(c.values())
        zh, n = c.most_common(1)[0]
        if total >= MIN_COUNT and n / total >= MIN_RATIO and zh != term:
            locked[term] = zh
    return locked

def clean_names_from_glossary():
    """Salvage clean EN-name / KR-sprite mappings from the earlier extraction."""
    g = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "glossary.json")))
    def ok(z):
        z = z.strip()
        if HANGUL.search(z) or re.search(r'[぀-ヿ]', z): return False
        if LATIN.search(z) and CJK.search(z): return False   # 'Seven协会 良秀' style mash
        return bool(z)
    out = {}
    for en, zh in g.get("names", {}).items():
        if len(en) >= 2 and ok(zh) and zh.strip() != en: out[en] = zh.strip()
    for kr, zh in g.get("model_sprite_to_zh", {}).items():
        if HANGUL.search(kr) and ok(zh): out[kr] = zh.strip()
    return out

# user-confirmed, authoritative (override everything)
USER = {"뿌이": "噗依", "통제자": "监督者", "Overseer": "监督者",
        "Jeanne": "让娜", "관리자": "经理", "관리자님": "经理",
        # verified against community gold 2026-09-30 (batch-test misses)
        "세븐": "Seven协会", "Seven": "Seven协会", "흐트러짐": "混乱",
        "시본": "海嗣"}

def main():
    kr_map, en_map, files = mine()
    kr_locked = consistent(kr_map)
    en_locked = consistent(en_map)
    print(f"files aligned: {files}")
    print(f"mined KR terms: {len(kr_locked)}  EN terms: {len(en_locked)}")
    # precedence: cleaned-names  <  mined-EN  <  mined-KR  <  user
    locked = {}
    locked.update(clean_names_from_glossary())
    locked.update(en_locked)
    locked.update(kr_locked)
    locked.update(USER)
    json.dump(locked, open(OUT, "w"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"TOTAL locked terms: {len(locked)} -> {OUT}")
    # spot-check
    for p in ["돈키호테", "뿌이", "통제자", "관리자", "세븐", "Don Quixote", "Heathcliff"]:
        print(f"  {p!r:>16} -> {locked.get(p)}   (kr n={sum(kr_map.get(p,{}).values())}, en n={sum(en_map.get(p,{}).values())})")

if __name__ == "__main__":
    main()
