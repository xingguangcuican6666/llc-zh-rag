import json, os, re
EN="en"; KR="kr"; JP="jp"
ZH="../../../Lang/LLC_zh-CN"
BLOCK={"id","key","index","model","codeName","undefined"}  # never translate
def load(p):
    with open(p,encoding="utf-8-sig") as f: return json.load(f)
def variants(rel):
    d=os.path.dirname(rel); b=os.path.basename(rel)
    j=lambda root,pfx: os.path.join(root,d,pfx+"_"+b) if d else os.path.join(root,pfx+"_"+b)
    return j(EN,"EN"), j(KR,"KR"), j(JP,"JP"), (os.path.join(ZH,d,b) if d else os.path.join(ZH,b))
def is_symbolic(s):
    # strings with no letters/hangul/kana/han -> not worth translating (keep as-is)
    return not re.search(r'[A-Za-z가-힣぀-ヿ一-鿿]', s)
def walk_strings(obj):
    """Yield (path, key, value) for every string, in deterministic order."""
    def rec(o, path):
        if isinstance(o, dict):
            for k in o:  # dict preserves insertion order
                v=o[k]
                if isinstance(v,str): yield (path+[k], k, v)
                else: yield from rec(v, path+[k])
        elif isinstance(o, list):
            for i,v in enumerate(o):
                if isinstance(v,str): yield (path+[i], None, v)
                else: yield from rec(v, path+[i])
    yield from rec(obj, [])
def translatable_units(rel):
    """Return list of {uid, path, key, en, kr, jp} for translatable strings, EN as base structure."""
    enp,krp,jpp,zhp = variants(rel)
    en=load(enp)
    kr=load(krp) if os.path.exists(krp) else None
    jp=load(jpp) if os.path.exists(jpp) else None
    en_items=list(walk_strings(en))
    kr_items=list(walk_strings(kr)) if kr is not None else []
    jp_items=list(walk_strings(jp)) if jp is not None else []
    # align by position (identical structure across langs)
    units=[]
    uid=0
    for idx,(path,key,val) in enumerate(en_items):
        translate = (key not in BLOCK) and (not is_symbolic(val))
        if not translate:
            continue
        krv = kr_items[idx][2] if idx < len(kr_items) else ""
        jpv = jp_items[idx][2] if idx < len(jp_items) else ""
        units.append({"uid":uid,"path":path,"key":key,"en":val,"kr":krv,"jp":jpv})
        uid+=1
    return en, en_items, units

def localize_dir():
    """游戏官方本地化目录 (.../Resources_moved/Localize)。
    优先取环境变量 $LLC_LOC；否则从当前工作目录（流水线通常在游戏
    LimbusCompany_Data 内运行）自动向上探测；都失败则报错。无任何硬编码路径。"""
    p = os.environ.get("LLC_LOC")
    if p and os.path.isdir(p):
        return p
    cur, seen = os.getcwd(), set()
    while cur and cur not in seen:
        seen.add(cur)
        cand = os.path.join(cur, "Assets", "Resources_moved", "Localize")
        if os.path.isdir(cand):
            return cand
        if os.path.basename(cur) == "Localize" and os.path.isdir(os.path.join(cur, "en")):
            return cur
        cur = os.path.dirname(cur)
    raise SystemExit("找不到游戏本地化目录：请设置环境变量 LLC_LOC 指向 .../Resources_moved/Localize")
