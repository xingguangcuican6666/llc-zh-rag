"""Incremental weekly pipeline: diff official KR vs last snapshot, translate only
the new/changed units with the RAG translator, merge into Lang/LLC_zh-CN, verify.

Usage:
  python3 incremental.py plan      # show what changed (new files, new/changed units)
  python3 incremental.py run       # translate the delta and write the zh files
  python3 incremental.py snapshot  # record current official KR as the baseline
"""
import os, sys, json, glob, hashlib, copy, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translate

LOC = common.localize_dir()
ZH_ROOT = os.path.join(LOC, "../../../Lang/LLC_zh-CN")
SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.json")

_HANGUL = re.compile(r'[가-힣]')

def needs_llm(u):
    """Only send genuine Korean prose to the model. Units whose KR has no Hangul
    (symbolic codes like '(800101, VERY_HIGH)', pure-Latin loanwords, numbers) are
    kept verbatim from the existing zh / EN template — the LLM would only corrupt
    them. Names carry Hangul (돈키호테) so they still translate via the glossary."""
    return bool(_HANGUL.search((u.get("kr") or "").strip()))

def h(s): return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]

def official_rels():
    """Every <name> that has an official EN+KR file (prefix stripped)."""
    rels = set()
    for enp in glob.glob(f"{LOC}/en/**/EN_*.json", recursive=True):
        rel = os.path.relpath(enp, f"{LOC}/en")
        d, b = os.path.dirname(rel), os.path.basename(rel)[3:]   # drop EN_
        rel2 = os.path.join(d, b) if d else b
        _, krp, _, _ = common.variants(rel2)
        if os.path.exists(krp):
            rels.add(rel2)
    return sorted(rels)

def set_by_path(obj, path, val):
    cur = obj
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = val

def diff():
    os.chdir(LOC)
    snap = json.load(open(SNAP)) if os.path.exists(SNAP) else {}
    new_files, changed = [], []   # changed: list of (rel, unit, kind)
    for rel in official_rels():
        _, _, units = common.translatable_units(rel)
        _, _, _, zhp = common.variants(rel)
        zh_exists = os.path.exists(zhp)
        fsnap = snap.get(rel, {})
        if not zh_exists:
            new_files.append(rel)
        for u in units:
            pk = "/".join(map(str, u["path"]))
            cur = h(u["kr"])
            if pk not in fsnap:
                changed.append((rel, u, "NEW" if zh_exists else "NEWFILE"))
            elif fsnap[pk] != cur:
                changed.append((rel, u, "CHANGED"))
    return new_files, changed

def snapshot():
    os.chdir(LOC)
    snap = {}
    for rel in official_rels():
        _, _, units = common.translatable_units(rel)
        snap[rel] = {"/".join(map(str, u["path"])): h(u["kr"]) for u in units}
    json.dump(snap, open(SNAP, "w"), ensure_ascii=False)
    print(f"snapshot: {len(snap)} files recorded -> {SNAP}")

def run():
    os.chdir(LOC)
    new_files, changed = diff()
    print(f"delta: {len(new_files)} new files, {len(changed)} new/changed units")
    # group units by file
    byfile = {}
    for rel, u, kind in changed:
        byfile.setdefault(rel, []).append(u)
    for rel, units in byfile.items():
        enp, krp, _, zhp = common.variants(rel)
        en_obj = common.load(enp)
        # start from existing zh if present else EN template
        if os.path.exists(zhp):
            zh_obj = common.load(zhp)
        else:
            zh_obj = copy.deepcopy(en_obj)
        n_tr, n_skip = 0, 0
        for u in units:
            if not needs_llm(u):          # codes/symbols/pure-Latin: keep verbatim
                n_skip += 1
                continue
            zh = translate.translate_unit({"kr": u["kr"], "en": u["en"]}, k=8)
            set_by_path(zh_obj, u["path"], zh)
            n_tr += 1
        os.makedirs(os.path.dirname(zhp) or ".", exist_ok=True)
        json.dump(zh_obj, open(zhp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  wrote {rel}: {n_tr} translated, {n_skip} kept verbatim")
    print("done. review, then run `snapshot` to baseline.")

def dryrun(limit=6):
    """Translate the current delta and PRINT proposed zh — writes no files.
    Used to preview a weekly update before committing it."""
    os.chdir(LOC)
    new_files, changed = diff()
    print(f"delta: {len(new_files)} new files, {len(changed)} new/changed units")
    shown = 0
    for rel, u, kind in changed:
        if shown >= limit:
            break
        if not needs_llm(u):              # would be kept verbatim by run(); don't preview as a translation
            continue
        zh = translate.translate_unit({"kr": u["kr"], "en": u["en"]}, k=8)
        print(f"\n[{kind}] {rel}")
        print(f"  KR : {u['kr'][:90]}")
        if u["en"]:
            print(f"  EN : {u['en'][:90]}")
        print(f"  ZH : {zh}")
        shown += 1
    print(f"\n(dry-run: translated {shown} of {len(changed)} delta units, no files written)")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "snapshot":
        snapshot()
    elif cmd == "run":
        run()
    elif cmd == "dryrun":
        dryrun(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    else:
        nf, ch = diff()
        print(f"new files: {len(nf)}")
        for r in nf[:10]: print("  +", r)
        print(f"new/changed units: {len(ch)}")
        from collections import Counter
        print("  by kind:", dict(Counter(k for _, _, k in ch)))
        for rel, u, kind in ch[:8]:
            print(f"  [{kind}] {rel}  {u['kr'][:40]}")
