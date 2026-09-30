"""Robust KR/EN/zh alignment.

2219/2257 community files share the official EN structure exactly -> path
alignment is valid. The other 38 drifted in dataList length -> align their
entries by `id`/`key` instead, so a term never maps to a shifted neighbour.
Returns clean (kr, en, zh) triples; callers keep raw frequencies for mining.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common

def struct(o):
    if isinstance(o, dict):  return ("d", tuple((k, struct(v)) for k, v in o.items()))
    if isinstance(o, list):  return ("l", tuple(struct(v) for v in o))
    return ("s",) if isinstance(o, str) else (type(o).__name__,)

def _entry_key(e):
    if isinstance(e, dict):
        for k in ("id", "key", "ID", "Key"):
            if k in e: return e[k]
    return None

def _entry_strings(e):
    """(field_key, value) for translatable string fields of one dataList entry."""
    for k, v in e.items():
        if k in common.BLOCK: continue
        if isinstance(v, str) and not common.is_symbolic(v):
            yield k, v

def _align_by_id(en, kr, zh):
    out = []
    de, dk, dz = en.get("dataList"), kr.get("dataList"), zh.get("dataList")
    if not (isinstance(de, list) and isinstance(dk, list) and isinstance(dz, list)):
        return out
    kmap = {_entry_key(e): e for e in dk if isinstance(e, dict)}
    zmap = {_entry_key(e): e for e in dz if isinstance(e, dict)}
    for e in de:
        if not isinstance(e, dict): continue
        eid = _entry_key(e)
        if eid is None or eid not in kmap or eid not in zmap: continue
        ke, ze = kmap[eid], zmap[eid]
        for fk, ev in _entry_strings(e):
            kv = ke.get(fk); zv = ze.get(fk)
            if isinstance(zv, str):
                out.append(((kv if isinstance(kv, str) else ""), ev, zv))
    return out

def aligned_pairs(rel):
    enp, krp, jpp, zhp = common.variants(rel)
    if not (os.path.exists(enp) and os.path.exists(krp) and os.path.exists(zhp)):
        return []
    try:
        en = common.load(enp); zh = common.load(zhp)
    except Exception:
        return []
    if struct(en) == struct(zh):
        _, _, units = common.translatable_units(rel)          # en/kr aligned by position
        zmap = {tuple(p): v for (p, k, v) in common.walk_strings(zh)}
        out = []
        for u in units:
            zv = zmap.get(tuple(u["path"]))
            if isinstance(zv, str):
                out.append((u["kr"] or "", u["en"] or "", zv))
        return out
    try:
        kr = common.load(krp)
    except Exception:
        return []
    return _align_by_id(en, kr, zh)
