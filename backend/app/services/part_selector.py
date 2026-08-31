# -*- coding: utf-8 -*-
"""part_selector —— 需求分析 skill 的唯一配件选型工具（AI 决策，工具落地）。

AI-first 原则：
- AI 决定“要什么/怎么配”：cpu/memory/drives/gpu/raid/
  nic 是唯一真值源（llm_extract_enhance 产出，slot_contract 对齐）。
  AI 在调用 select_parts 前补全模糊项（内存拆条、硬盘接口、GPU 型号等）。
- 工具只做“检索 + 落地”：料号/价格/规格全部来自 KP 库真实返回；未命中白盒 unmatched，
  绝不静默回退固定规则。
- 类目/规则词全部来自 requirement_rule_catalog 与 KP 库，不在代码里写死。
"""
from __future__ import annotations

import re
from typing import Optional

from app.repository.kp_repo import KPRepository

def _placeholder(db_cat, qty, want):
    """确定性占位缺口行：把客户登记的需求原样呈现给 AI 选型，引擎不做预测。"""
    return _row(db_cat, None, int(qty or 1), unmatched=True,
                reason="交由 AI 语义选型（引擎仅检索候选、不预判）",
                request_spec=str(want or ""))

def _capacity_mismatch(grounded_cap: Optional[float], need_cap: Optional[float],
                       cmp: str, tolerance_ratio: float) -> bool:
    """容量是否符合请求；None 表示不校验。"""
    if grounded_cap is None or need_cap is None:
        return False
    if cmp == "gte":
        return grounded_cap < need_cap
    if cmp == "lte":
        return grounded_cap > need_cap
    return abs(grounded_cap - need_cap) > max(1.0, need_cap * tolerance_ratio)

def _norm_model(value) -> str:
    """料号/型号文本归一：忽略大小写、空格、连字符，便于 LLM 输出与库内料号对齐。"""
    return re.sub(r"[\s\-_]+", "", str(value or "")).lower()

def _num_of(value) -> Optional[float]:

    if value is None:
        return None
    m = re.search(r"[\d.]+", str(value))
    return float(m.group()) if m else None

def _gb_of(value) -> Optional[float]:
    """容量词 → GB：'960G'/'32 GB'→960/32；'1.92T'/'1.92 TB'→1966.08。"""
    s = str(value or "").strip().upper()
    m = re.search(r"([\d.]+)\s*(T|G|M)?\s*B?", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "")
    if unit == "T":
        n *= 1024
    elif unit == "M":
        n /= 1024
    return n

def _series_ok(applicable, series: str) -> bool:
    """机型适配判定（与 kp_config API 同一语义）：applicable 缺省/无 series 键=通用件；
    series 列表含目标系列=适配；空列表=对全部系列隐藏。"""
    if not series or not isinstance(applicable, dict):
        return True
    lst = applicable.get("series")
    if lst is None:
        return True
    if isinstance(lst, list):
        return any(str(x).strip() == series for x in lst)
    return True

class _SeriesScopedRepo:
    """系列作用域包装：机型锁定后，配件候选池只剩适配件（含通用件）。
    过滤发生在取数边界，_ground_* 各 grounding 无需各自感知兼容性。"""

    def __init__(self, repo, series: str):
        self._repo = repo
        self._series = (series or "").strip()

    def __getattr__(self, name):
        return getattr(self._repo, name)

    def _f(self, rows):
        if not self._series:
            return rows
        return [r for r in rows if _series_ok(r.get("applicable"), self._series)]

    def get_by_category(self, category, search=""):
        return self._f(self._repo.get_by_category(category, search))

    def get_by_category_with_specs(self, category):
        return self._f(self._repo.get_by_category_with_specs(category))

    def get_by_category_with_spec_filter(self, category, spec_filters):
        return self._f(self._repo.get_by_category_with_spec_filter(category, spec_filters))

    def get_latest_prices(self, **kw):
        return self._f(self._repo.get_latest_prices(**kw))

def _cap_disp(gb: float) -> str:
    g = int(round(gb))
    if g % 1024 == 0:
        return f"{g // 1024}T"
    if g >= 1024:
        t = g / 1024
        s = f"{t:.2f}".rstrip("0").rstrip(".")
        return f"{s}T"
    return f"{g}G"

def _drive_media_label(row: dict) -> str:
    """盘介质标签：优先取目录规格 Type+Media（如 'SATA SSD'/'NVMe HDD'），
    无规格时按型号关键词兜底 SSD/HDD，保证展示与目录事实一致、不丢子类型。"""
    specs = row.get("specs") or {}
    bits = [str(specs.get("Type") or "").strip(), str(specs.get("Media") or "").strip()]
    label = " ".join(b for b in bits if b).upper()
    if label:
        return label
    hay = str(row.get("model") or "").upper()
    if "SSD" in hay:
        return "SSD"
    return "HDD"

def _drive_display(row: dict) -> str:
    """硬盘展示名：目录真实型号 + 介质子类型（如 '8T SATA SSD'），绝不改成 '2x 8T SSD'。"""
    model = str(row.get("model") or "").strip()
    media = _drive_media_label(row)
    if model and media.lower() not in model.lower():
        return f"{model} {media}"
    return model or media

def _spec_hit(specs: dict, filters: list) -> str:
    """规格 AND 过滤；全中返回标签串，否则 ''。"""
    hits = []
    for f in filters or []:
        sk = (f.get("spec_key") or "").strip()
        op = (f.get("op") or "=").strip()
        val = f.get("value")
        if not sk:
            continue
        sv = specs.get(sk)
        if sv is None:
            return ""
        svn = _num_of(sv)
        vn = _num_of(val) if not isinstance(val, list) else None
        if op in (">=", "<=", ">", "<") and svn is not None and vn is not None:
            ok = (svn >= vn if op == ">=" else svn <= vn if op == "<="
                  else svn > vn if op == ">" else svn < vn)
            if not ok:
                return ""
            hits.append(f"{sk}{op}{vn:g}")
        elif isinstance(val, list) or op == "in":
            vals = val if isinstance(val, list) else [val]
            if not any(str(sv).strip() == str(v).strip() for v in vals):
                return ""
            hits.append(f"{sk}∈{{{','.join(str(v) for v in vals)}}}")
        else:
            if str(sv).strip() != str(val).strip() and (svn is None or vn is None or abs(svn - vn) > 1e-9):
                return ""
            hits.append(f"{sk}={sv}")
    return " · ".join(hits)

def _pick(rows, mode):
    if not rows:
        return None
    if mode == "max_price":
        return max(rows, key=lambda r: float(r.get("price") or 0))
    if mode == "first":
        return rows[0]
    return min(rows, key=lambda r: float(r.get("price") or 0))

def _row(db_cat, rep, qty, matched_spec="", unmatched=False, reason="",
         request_spec="", grounded_spec="", spec_mismatch=False):
    return {
        "category": db_cat,
        "pn": str(rep.get("model") or "") if rep else "",
        "name": str(rep.get("model") or "") if rep else "",
        "unit_price": float(rep.get("price") or 0) if rep else 0.0,
        "currency": str(rep.get("currency") or "RMB") if rep else "RMB",
        "qty": int(qty or 1),
        "matched_spec": matched_spec or "",
        "unmatched": unmatched,
        "unmatched_reason": reason,
        "request_spec": request_spec or "",
        "grounded_spec": grounded_spec or "",
        "spec_mismatch": bool(spec_mismatch),
    }

def _unmatched(db_cat, qty, reason):
    return _row(db_cat, None, qty, unmatched=True, reason=reason)

def _category_index(repo):
    from app.services.requirement_rule_catalog import category_aliases
    aliases = category_aliases()
    db = {}
    for r in repo.get_categories():
        c = str(r.get("category") or "").strip()
        if c:
            db[c.lower()] = {"db_category": c, "count": int(r.get("count") or 0)}

    def find_db(key, alist):
        cand = []
        seen = set()

        def add(name):
            info = db.get(str(name).strip().lower())
            if info and info["db_category"] not in seen:
                seen.add(info["db_category"])
                cand.append(info)

        add(key)
        for a in alist:
            add(a)
        if cand:
            return max(cand, key=lambda x: x["count"])
        for c, info in db.items():
            kl = key.lower()
            if kl and (kl in c or c in kl):
                cand.append(info)
            elif any(str(a).strip().lower() and str(a).strip().lower() in c for a in alist):
                cand.append(info)
        return max(cand, key=lambda x: x["count"]) if cand else None

    by_key = {}
    for key, alist in aliases.items():
        best = find_db(key, alist)
        by_key[key] = {
            "key": key,
            "db_category": best["db_category"] if best else None,
            "count": best["count"] if best else 0,
            "aliases": [str(a) for a in alist if str(a).strip()],
        }
    return {"by_key": by_key, "db_lower": set(db.keys())}

def list_kp_categories():
    """返回真实配件类目（规则键 + 库类目 + 数量），供 AI 查真实类目而非猜词。"""
    repo = KPRepository()
    try:
        index = _category_index(repo)
        return [dict(e) for e in index["by_key"].values()]
    finally:
        repo.close()

def _search_category_names(repo, index):
    return [info["db_category"] for info in index["by_key"].values() if info.get("db_category")]

def _dedupe_rows(rows):
    out = []
    seen = set()
    for r in rows or []:
        key = (str(r.get("category") or ""), str(r.get("model") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def resolve_part_alias(term, category=None):
    """自由术语 → 目录候选（仅名称检索；别名/模型 token 等语义判断一律交由 AI 角色）。
    返回库内真实候选，不做静默顶替，不编造料号。"""
    repo = KPRepository()
    try:
        index = _category_index(repo)
        db_cat = _resolve_db_category(category, index) if category else None
        term = str(term or "").strip()
        rows = []
        if db_cat:
            rows = repo.get_by_category(db_cat, search=term)
        else:
            for c in _search_category_names(repo, index):
                rows.extend(repo.get_by_category(c, search=term))
        rows = _dedupe_rows(rows)
        out = []
        for r in rows:
            out.append({
                "category": r.get("category") or "",
                "pn": r.get("model") or "",
                "name": r.get("model") or "",
                "unit_price": float(r.get("price") or 0),
                "currency": r.get("currency") or "RMB",
                "reason": "名称检索",
            })
        return {"count": len(out), "candidates": out[:10], "reason": "名称检索"}
    finally:
        repo.close()

def compose_memory(total_gb, slots=None):
    """内存容量组合求解：total_gb → 库内可行单条容量组合（如 128G → 64G×2 / 32G×4）。"""
    repo = KPRepository()
    try:
        rows = repo.get_by_category_with_specs("Memory")
        caps = set()
        for r in rows:
            cap = _gb_of((r.get("specs") or {}).get("Capacity"))
            if cap and cap >= 4:
                caps.add(int(cap))
        comps = []
        for c in sorted(caps, reverse=True):
            qty = int(total_gb // c)
            if qty >= 1 and total_gb % c == 0:
                comps.append({"per_stick_gb": c, "qty": qty, "total_gb": int(total_gb)})
        note = ""
        if slots is not None and comps:
            comps = [c for c in comps if c["qty"] <= int(slots)]
            note = f"已按 {slots} 槽位过滤"
        return {"total_gb": int(total_gb), "compositions": comps[:5], "note": note}
    finally:
        repo.close()

def _candidate_desc(c: dict) -> str:
    """把候选的规格字典压成一行可读能力描述，供 AI 做语义匹配（非词表穷举）。"""
    model = str(c.get("model") or c.get("pn") or "").strip()
    specs = c.get("specs")
    bits = [model]
    if isinstance(specs, dict):
        for k, v in specs.items():
            if v in (None, "", []):
                continue
            bits.append(f"{k}:{v}")
    elif isinstance(specs, list):
        for item in specs:
            if isinstance(item, dict):
                for k, v in item.items():
                    if v not in (None, "", []):
                        bits.append(f"{k}:{v}")
    return "；".join(b for b in bits if b)

def retrieve_part_candidates(categories=None, server_type_name: str = "", series: str = "",
                             signals: Optional[dict] = None) -> dict:
    """按类目从 KP 库检索候选配件（只检索、不做语义/别名/规格匹配）。

    候选=库内真实件：id/model/desc(可读能力)/specs/price/applicable。series 只在候选池过滤，
    不参与型号/规格匹配。返回 {db_category: [candidate, ...]}；类目来自 categories 或
    signals（cpu/memory/drives/gpu/raid/nic）。
    """
    raw = KPRepository()
    try:
        repo = _SeriesScopedRepo(raw, series)
        index = _category_index(repo)
        db_cats: list = []

        def _add(raw_cat: str) -> None:
            dbc = _resolve_db_category(str(raw_cat), index)
            if dbc and dbc not in db_cats:
                db_cats.append(dbc)

        for c in (categories or []):
            _add(c)
        sig = signals or {}
        _exists = lambda v: isinstance(v, (list, dict)) and len(v) > 0
        if _exists(sig.get("cpu")):
            _add("CPU")
        if _exists(sig.get("memory")):
            _add("Memory")
        if _exists(sig.get("drives")):
            _add("HDD/SSD")
        if _exists(sig.get("gpu")):
            _add("GPU")
        if _exists(sig.get("raid")):
            _add("Raid card")
        if _exists(sig.get("nic")):
            _add("NIC")
        if not db_cats and server_type_name:
            from app.services.requirement_rule_catalog import type_packages
            for pkg in type_packages() or []:
                kw = str(pkg.get("type_keyword") or "")
                if kw and kw in server_type_name:
                    for c in (pkg.get("categories") or []):
                        _add(c)
                    break
        out: dict = {}
        for dbc in db_cats:
            rows = repo.get_by_category_with_specs(dbc) or []
            cands = []
            for r in rows:
                cand = dict(r)
                cand["pn"] = str(cand.get("model") or "")
                cand["name"] = str(cand.get("model") or "")
                cand["unit_price"] = float(cand.get("price") or 0)
                cand["desc"] = _candidate_desc(cand)
                cands.append(cand)
            out[dbc] = cands
        return out
    finally:
        raw.close()

def _resolve_db_category(need_cat, index):
    n = str(need_cat or "").strip()
    if not n:
        return None
    nl = n.lower()
    if nl in index["db_lower"]:
        return n
    if nl in index["by_key"]:
        return index["by_key"][nl]["db_category"]
    for e in index["by_key"].values():
        if any(a.lower() == nl for a in e["aliases"]):
            return e["db_category"]
    for e in index["by_key"].values():
        kl = e["key"].lower()
        if kl and (kl in nl or nl in kl):
            return e["db_category"]
        if any(a.lower() and (a.lower() in nl or nl in a.lower()) for a in e["aliases"]):
            return e["db_category"]
    return None

def _ground_cpu(repo, db_cat, sig, pick):
    """CPU：不做型号/别名/规格匹配（旧解析器已删除），只把登记信号转成「交由 AI 选型」缺口行。"""
    if not isinstance(sig, dict) or not sig:
        return []
    qty = int((sig or {}).get("qty") or 1)
    model = str((sig or {}).get("model") or "").strip()
    cores = sig.get("cores")
    tdp = sig.get("tdp_w")
    bits = [model] if model else ["未指定型号"]
    if cores:
        bits.append(f"{int(cores)}C")
    if tdp:
        bits.append(f"{int(tdp)}W")
    return [_placeholder(db_cat, qty, " ".join(bits))]

def _ground_memory(repo, db_cat, sig, pick):
    """内存：只把登记信号（容量/类型/速度）转成缺口行，由 AI 从候选选条。"""
    if not isinstance(sig, dict) or not sig:
        return []
    qty = int(sig.get("qty") or 1)
    bits = []
    if sig.get("per_stick_gb"):
        bits.append(f"{int(sig['per_stick_gb'])}G")
    if sig.get("total_gb"):
        bits.append(f"共{int(sig['total_gb'])}G")
    if sig.get("type"):
        bits.append(str(sig["type"]))
    if sig.get("speed"):
        bits.append(str(sig["speed"]))
    return [_placeholder(db_cat, qty, " ".join(bits) or "内存")]

def _ground_drives(repo, db_cat, groups, pick):
    """硬盘：每个盘组 → 一行缺口（容量/接口/介质），由 AI 从候选按需求语义选型。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        capacity = str(g.get("capacity") or g.get("term") or "").strip()
        interface = str(g.get("interface") or g.get("kind") or "").strip()
        media = str(g.get("media") or "").strip()
        want = " ".join(b for b in (capacity, interface, media) if b) or "硬盘"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_gpu(repo, db_cat, groups, pick):
    """GPU：每个 GPU 组 → 一行缺口（型号 token/显存），由 AI 从候选按需求语义选型。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        tokens = [str(t) for t in (g.get("tokens") or []) if str(t).strip()]
        cap = g.get("cap") if g.get("cap") is not None else g.get("capacity_gb")
        want = " ".join(tokens) or "未指定型号"
        if cap is not None:
            want = f"{want} {cap}G显存"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_raid(repo, db_cat, groups, pick):
    """RAID：只登记卡需求（型号/缓存/级别），由 AI 从阵列卡候选选型；不做 RAID Level 词表匹配。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        model = str(g.get("model") or "").strip()
        cache = g.get("cache")
        levels = g.get("raid_levels") or []
        bits = [model] if model else ["RAID 阵列卡"]
        if cache:
            bits.append(f"{cache}缓存")
        if levels:
            bits.append("支持" + "/".join(str(x) for x in levels))
        out.append(_placeholder(db_cat, qty, " ".join(bits)))
    return out

def _ground_nic(repo, db_cat, msf, pick):
    """网卡：把多规格需求转成缺口行（含修饰词），由 AI 从候选选型。"""
    if isinstance(msf, dict):
        lines = msf.get("Network(NIC) requirement") or msf.get(db_cat) or []
    elif isinstance(msf, list):
        lines = msf
    else:
        lines = []
    if isinstance(lines, dict):
        lines = [lines]
    if not isinstance(lines, list):
        lines = []
    out = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        qty = int(line.get("qty") or 1)
        terms = line.get("name_contains") or []
        if not isinstance(terms, list):
            terms = [terms]
        want = " ".join(str(t) for t in terms if str(t).strip()) or "网卡"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_generic(repo, db_cat, search, qty_map, search_map, pick):
    """通用类（电源等）：把关键词/数量转成缺口行，由 AI 从候选选型。"""
    qty = int((qty_map or {}).get(db_cat) or 1)
    kw = str((search_map or {}).get(db_cat) or search or "").strip()
    return [_placeholder(db_cat, qty, kw or str(db_cat))]

def select_parts(categories=None, server_type_name=None, search=None, qty_map=None, search_map=None,
                 representative_pick="min_price",
                 cpu=None, memory=None, drives=None,
                 gpu=None, raid=None, psu=None, nic=None,
                 series: str = ""):
    """按结构化信号落地真实料号；AI 补全信号（怎么配），工具只检索落地。

    series：机型平台系列——已锁机型时传入，候选池过滤到适配件（applicable 语义），
    不兼容件进 BOM 是硬错误；未锁机型/未知系列传空。
    """
    pick = lambda rows: _pick(rows, representative_pick)
    raw_repo = KPRepository()
    repo = _SeriesScopedRepo(raw_repo, series)
    try:
        index = _category_index(repo)
        db_cats = []

        def _add_cat(raw_cat: str) -> None:
            dbc = _resolve_db_category(str(raw_cat), index)
            if dbc and dbc not in db_cats:
                db_cats.append(dbc)

        for c in (categories or []):
            _add_cat(c)
        # 信号字段是唯一真值源：categories 只是编排辅助，漏了某项也不能把该类配件丢掉。
        if isinstance(cpu, dict) and cpu:
            _add_cat("CPU")
        if memory:
            _add_cat("Memory")
        if drives:
            _add_cat("HDD/SSD")
        if gpu:
            _add_cat("GPU")
        if raid:
            _add_cat("Raid card")
        if nic:
            _add_cat("NIC")
        if not db_cats and server_type_name:
            from app.services.requirement_rule_catalog import type_packages
            for pkg in type_packages():
                kw = str(pkg.get("type_keyword") or "")
                if kw and kw in server_type_name:
                    for c in (pkg.get("categories") or []):
                        _add_cat(c)
                    break
        db_cats = [c for c in dict.fromkeys(db_cats) if c]

        parts = []
        for db_cat in db_cats:
            low = db_cat.lower()
            if low == "cpu":
                parts.extend(_ground_cpu(repo, db_cat, cpu, pick))
            elif low == "memory":
                parts.extend(_ground_memory(repo, db_cat, memory, pick))
            elif low in ("hdd/ssd", "ssd", "storage hdd/ssd"):
                parts.extend(_ground_drives(repo, db_cat, drives, pick))
            elif low in ("gpu", "gpu card"):
                parts.extend(_ground_gpu(repo, db_cat, gpu, pick))
            elif "raid" in low or "hba" in low:
                parts.extend(_ground_raid(repo, db_cat, raid, pick))
            elif "nic" in low or "network" in low:
                parts.extend(_ground_nic(repo, db_cat, nic, pick))
            else:
                parts.extend(_ground_generic(repo, db_cat, search, qty_map, search_map, pick))
        return parts
    finally:
        raw_repo.close()

# ── 场景化配件推荐（要了配件但零信号时的缺口选项；全部目录事实）──────────────────

_SCENARIO_SLOT_OF_DB_CAT = [
    (("gpu",), "gpu", "GPU 加速卡"),
    (("cpu",), "cpu", "CPU"),
    (("memory", "mem"), "memory", "内存"),
    (("hdd/ssd", "ssd", "storage", "drive"), "drives", "硬盘"),
    (("raid", "hba"), "raid", "阵列卡"),
]

def _scenario_slot_for(db_cat: str) -> tuple[str, str]:
    low = db_cat.lower()
    for keys, slot, label in _SCENARIO_SLOT_OF_DB_CAT:
        if any(k in low for k in keys):
            return slot, label
    return "", ""

def _scenario_categories(server_type_name: str) -> list:
    """场景包命中的品类（数据源=system_config 规则目录 type_packages，与 select_parts 同判定）。"""
    n = str(server_type_name or "").strip()
    if not n:
        return []
    from app.services.requirement_rule_catalog import type_packages
    for pkg in type_packages() or []:
        kw = str(pkg.get("type_keyword") or "")
        if kw and kw in n:
            return [str(c) for c in (pkg.get("categories") or [])]
    return []

def scenario_parts_gap_data(server_type_name: str, baseline=None, ext=None,
                            include_price: bool = True, only_unfilled: bool = False) -> tuple:
    """场景化配件推荐缺口数据（逐组问）：(reason_code, options) 只含第一个
    未填且未跳过的组；选完一组续跑引擎，下一组自然接上。无场景包/组全空 → ("", [])。

    选项全部来自目录事实：品类=场景包；型号/容量=KP 目录并按机型系列过滤（applicable）；
    数量上限=机箱能力（GPU 槽/内存槽/CPU 路）。每个选项附带结构化 signal 载荷
    （apply_structured_slots 直传形态）+ 数量元数据（qty/qty_max/unit_gb 供前端
    stepper 与实时总量显示），点击即原样落信号槽，客户端不解析文本。
    逃生项：「先跳过这组」登记 scenario_skips（引擎后续不再问该组）；
    only_unfilled=True 时另附「就这些」终止补齐项。
    """
    baseline = baseline or {}
    ext = ext or {}
    series = str(baseline.get("series") or "").strip()
    cats = _scenario_categories(server_type_name)
    if not cats:
        return "", []
    reason = "scenario_incomplete" if only_unfilled else "scenario_recommend"

    def _price_note(row, qty=1):
        if not include_price or not row:
            return ""
        try:
            v = float(row.get("price") or 0) * qty
        except (TypeError, ValueError):
            return ""
        return f"¥{v:,.0f}" if v > 0 else ""

    repo = KPRepository()
    try:
        srepo = _SeriesScopedRepo(repo, series)
        index = _category_index(srepo)
        db_cats = []
        for c in cats:
            dbc = _resolve_db_category(c, index)
            if dbc and dbc not in db_cats:
                db_cats.append(dbc)
        compat = f"{series} 适配" if series else ""
        skips = {str(s).strip() for s in (ext.get("scenario_skips") or []) if str(s).strip()}
        out: list[dict] = []
        cur_slot, cur_label = "", ""
        for dbc in db_cats:
            slot, label = _scenario_slot_for(dbc)
            if not slot or slot in skips or (only_unfilled and ext.get(slot)):
                continue
            rows = srepo.get_by_category_with_specs(dbc)

            def specs_of(r):
                return r.get("specs") or {}

            if slot == "gpu":
                def gcap(r):
                    return _gb_of(specs_of(r).get("Capacity"))
                ranked = sorted((r for r in rows if gcap(r)), key=lambda r: -gcap(r))
                if not ranked:
                    continue
                # 候选多样性：取前 2 个**不同型号**（只出"最大显存件"单一候选像兜底，
                # 客户没得挑）；数量档（满配/半配）跟在型号后面
                top_models: list = []
                _seen: set = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if m and m not in _seen:
                        _seen.add(m)
                        top_models.append(r)
                    if len(top_models) >= 2:
                        break
                slots_n = int(baseline.get("gpu_slots") or 0)
                for top in top_models:
                    tiers = sorted({q2 for q2 in (slots_n, slots_n // 2) if q2 >= 1}) if slots_n else [1]
                    for q in tiers[:2]:
                        note = " ".join(b for b in (f"{int(gcap(top))}G 显存", compat, _price_note(top, q)) if b)
                        out.append({"label": f"{q}× {top.get('model')}", "value": f"{q}×{top.get('model')}",
                                    "desc": note, "slot": slot, "group": label,
                                    "qty": int(q), "qty_max": slots_n or 8, "unit_gb": int(gcap(top)),
                                    "signal": {"gpu": [{"model": str(top.get("model") or ""), "qty": int(q)}]}})
            elif slot == "cpu":
                def cores(r):
                    return _num_of(specs_of(r).get("Cores"))
                ranked = sorted((r for r in rows if cores(r)), key=lambda r: -cores(r)) \
                    or sorted(rows, key=lambda r: -float(r.get("price") or 0))
                if not ranked:
                    continue
                # 前 3 个不同型号（平台适配范围内核数降序），客户可挑性价比而非只有"最多核"
                best_models: list = []
                _seen2: set = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if m and m not in _seen2:
                        _seen2.add(m)
                        best_models.append(r)
                    if len(best_models) >= 3:
                        break
                q = int(baseline.get("max_cpu") or 1)
                for best in best_models:
                    note = " ".join(b for b in (f"{int(cores(best))} 核" if cores(best) else "",
                                                compat, _price_note(best, q)) if b)
                    out.append({"label": f"{q}× {best.get('model')}", "value": f"{q}×{best.get('model')}",
                                "desc": note, "slot": slot, "group": label,
                                "signal": {"cpu": {"model": str(best.get("model") or ""), "qty": int(q)}}})
            elif slot == "memory":
                def mcap(r):
                    return _gb_of(specs_of(r).get("Capacity"))
                caps = sorted({int(c) for c in (mcap(r) for r in rows) if c}, reverse=True)[:2]
                if not caps:
                    continue
                dimm = int(baseline.get("max_dimm") or 0)
                for c in caps:
                    n = dimm if dimm else 8
                    stick = next((r for r in rows if mcap(r) == c), None)
                    note = " ".join(b for b in (
                        f"插满 {dimm} 槽" if dimm else "按 8 条估（机型未登记内存槽数）",
                        str((specs_of(stick) or {}).get("Type") or "").strip(),
                        compat, _price_note(stick, n)) if b)
                    out.append({"label": f"{n}× {c}G（共 {n * c}G）", "value": f"{n}×{c}G",
                                "desc": note, "slot": slot, "group": label,
                                "qty": int(n), "qty_max": dimm or 8, "unit_gb": int(c),
                                "signal": {"memory": {"per_stick_gb": int(c), "qty": int(n)}}})
            elif slot == "drives":
                def dcap(r):
                    return _gb_of(specs_of(r).get("Capacity"))
                is_ssd = [r for r in rows if "SSD" in (
                    str(specs_of(r).get("Media") or "") + str(specs_of(r).get("Type") or "")).upper()]
                pool = is_ssd or rows
                caps = sorted({int(c) for c in (dcap(r) for r in pool) if c}, reverse=True)[:2]
                for c in caps:
                    def cap_of(r):
                        v = dcap(r)
                        return int(round(v)) if v else None
                    stick = next((r for r in pool if cap_of(r) == c), None)
                    if stick is None:
                        continue
                    disp = _drive_display(stick)
                    media = _drive_media_label(stick)
                    sig_item = {"capacity_gb": int(c), "qty": 1, "media": media}
                    out.append({"label": disp,
                                "value": disp,
                                "desc": " ".join(b for b in (media, compat,
                                                             _price_note(stick, 1)) if b),
                                "slot": slot, "group": label,
                                "qty": 1, "qty_max": 16, "unit_gb": int(c),
                                "signal": {"drives": [sig_item]}})
            elif slot == "raid":
                if not rows:
                    continue
                card = min(rows, key=lambda r: float(r.get("price") or 0))
                out.append({"label": "RAID 10 阵列卡", "value": "RAID 10",
                            "desc": " ".join(b for b in ("数据安全镜像", compat, _price_note(card)) if b),
                            "slot": slot, "group": label,
                            "signal": {"raid": [{"raid_levels": ["10"]}]}})
            if out:
                cur_slot, cur_label = slot, label
                break
        if not out:
            return "", []
        out.append({"label": f"先跳过这组（暂不配{cur_label}）", "value": "skip_group",
                    "desc": "跳过本组推荐，继续确认下一项", "slot": "kp_scenario_skip",
                    "group": "", "signal": {"scenario_skips": [cur_slot]}})
        if only_unfilled:
            out.append({"label": "就这些，按已选的出方案", "value": "scenario_complete",
                        "desc": "跳过剩余推荐项，直接生成方案", "slot": "kp_scenario_done",
                        "group": ""})
        return reason, out
    finally:
        repo.close()

def manual_pick_options(slot: str, server_type_name: str, baseline=None,
                        include_price: bool = True, limit: int = 40) -> list:
    """配件库自选候选：槽位品类在平台系列适配内的全部件（带 signal 载荷）。

    场景推荐只出 top-N 启发式候选（客户没得挑）；自选=全目录平铺按容量/核数
    降序，客户按型号/价格自己定。候选由服务端生成并登记进 last_card（与发卡
    选项同源同格式），后续点击仍走 (slot,value) 留底匹配，客户端不携带 signal。
    内存/硬盘按容量去重（信号就是容量），同容量取最便宜型号做代表。
    """
    baseline = baseline or {}
    series = str(baseline.get("series") or "").strip()
    meta = next(((keys, s, label) for keys, s, label in _SCENARIO_SLOT_OF_DB_CAT if s == slot), None)
    if not meta or slot == "raid":
        return []
    keys, _, label = meta
    repo = KPRepository()
    try:
        srepo = _SeriesScopedRepo(repo, series)
        index = _category_index(srepo)
        db_cats = []
        for c in (repo.get_categories() or []):
            name = str(c.get("category") or "").strip()
            if name and any(k in name.lower() for k in keys):
                dbc = _resolve_db_category(name, index)
                if dbc and dbc not in db_cats:
                    db_cats.append(dbc)
        compat = f"{series} 适配" if series else ""

        def _price_note(row, qty=1):
            if not include_price or not row:
                return ""
            try:
                v = float(row.get("price") or 0) * qty
            except (TypeError, ValueError):
                return ""
            return f"¥{v:,.0f}" if v > 0 else ""

        def specs_of(r):
            return r.get("specs") or {}

        out: list[dict] = []
        for dbc in db_cats:
            rows = srepo.get_by_category_with_specs(dbc)
            if slot == "gpu":
                slots_n = int(baseline.get("gpu_slots") or 0)
                tiers = sorted({q for q in (slots_n, slots_n // 2, 1) if q >= 1})[-2:] if slots_n else [1]
                ranked = sorted(rows, key=lambda r: -(_gb_of(specs_of(r).get("Capacity")) or 0))
                seen: set = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if not m or m in seen:
                        continue
                    seen.add(m)
                    cap = _gb_of(specs_of(r).get("Capacity"))
                    for q in tiers:
                        note = " ".join(b for b in (
                            f"{int(cap)}G 显存" if cap else "", compat, _price_note(r, q)) if b)
                        out.append({"label": f"{q}× {m}", "value": f"{q}×{m}",
                                    "desc": note, "slot": slot, "group": label,
                                    "signal": {"gpu": [{"model": m, "qty": int(q)}]}})
            elif slot == "cpu":
                q = int(baseline.get("max_cpu") or 1)
                ranked = sorted(rows, key=lambda r: -(_num_of(specs_of(r).get("Cores")) or 0))
                seen = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if not m or m in seen:
                        continue
                    seen.add(m)
                    cores_v = _num_of(specs_of(r).get("Cores"))
                    note = " ".join(b for b in (
                        f"{int(cores_v)} 核" if cores_v else "", compat, _price_note(r, q)) if b)
                    out.append({"label": f"{q}× {m}", "value": f"{q}×{m}",
                                "desc": note, "slot": slot, "group": label,
                                "signal": {"cpu": {"model": m, "qty": int(q)}}})
            elif slot == "memory":
                dimm = int(baseline.get("max_dimm") or 0) or 8
                by_cap: dict[int, dict] = {}
                for r in rows:
                    c = _gb_of(specs_of(r).get("Capacity"))
                    if not c:
                        continue
                    k = int(c)
                    if k not in by_cap or float(r.get("price") or 1e9) < float(by_cap[k].get("price") or 1e9):
                        by_cap[k] = r
                for c, r in sorted(by_cap.items(), key=lambda kv: -kv[0]):
                    note = " ".join(b for b in (
                        f"插满 {dimm} 槽" if int(baseline.get("max_dimm") or 0) else "按 8 条估（机型未登记内存槽数）",
                        str(specs_of(r).get("Type") or "").strip(),
                        str(specs_of(r).get("Speed") or "").strip(), compat,
                        _price_note(r, dimm)) if b)
                    out.append({"label": f"{dimm}× {c}G（共 {dimm * c}G）", "value": f"{dimm}×{c}G",
                                "desc": note, "slot": slot, "group": label,
                                "signal": {"memory": {"per_stick_gb": int(c), "qty": int(dimm)}}})
            elif slot == "drives":
                by_cap: dict[tuple, dict] = {}
                for r in rows:
                    c = _gb_of(specs_of(r).get("Capacity"))
                    if not c:
                        continue
                    media = "SSD" if "SSD" in (str(specs_of(r).get("Media") or "") +
                                              str(specs_of(r).get("Type") or "")).upper() else "HDD"
                    k = (int(c), media)
                    if k not in by_cap or float(r.get("price") or 1e9) < float(by_cap[k].get("price") or 1e9):
                        by_cap[k] = r
                for (c, _mk), r in sorted(by_cap.items(), key=lambda kv: -kv[0][0]):
                    disp = _drive_display(r)
                    media = _drive_media_label(r)
                    note = " ".join(b for b in (media, compat, _price_note(r, 1)) if b)
                    out.append({"label": disp, "value": disp,
                                "desc": note, "slot": slot, "group": label,
                                "qty": 1, "qty_max": 16, "unit_gb": int(c),
                                "signal": {"drives": [{"capacity_gb": int(c), "qty": 1,
                                                       "media": media}]}})
        return out[:limit]
    finally:
        repo.close()

def manual_signal_for_text(slot: str, text: str, server_type_name: str,
                           baseline=None) -> Optional[dict]:
    """自由输入型号 → 目录匹配构造 signal（逐项卡「手动输入型号」入口）。

    系列适配内全目录按 归一化型号检索 对**型号原文**匹配（型号级命中，不经容量去重代表）；
    数量取该槽默认档（GPU=满配 / CPU=路数 / 内存=插满 / 硬盘=1，前端 stepper 可再调）。
    未命中返回 None——调用方走登记表路径白盒处理（库外项不拦截）。
    """
    text = str(text or "").strip()
    meta = next(((keys, s, label) for keys, s, label in _SCENARIO_SLOT_OF_DB_CAT if s == slot), None)
    if not meta or not text or slot not in ("gpu", "cpu", "memory", "drives"):
        return None
    keys, _, _label = meta
    baseline = baseline or {}
    series = str(baseline.get("series") or "").strip()
    repo = KPRepository()
    try:
        srepo = _SeriesScopedRepo(repo, series)
        index = _category_index(srepo)
        for c in (repo.get_categories() or []):
            name = str(c.get("category") or "").strip()
            if not name or not any(k in name.lower() for k in keys):
                continue
            dbc = _resolve_db_category(name, index)
            if not dbc:
                continue
            for r in (srepo.get_by_category_with_specs(dbc) or []):
                m = str(r.get("model") or "")
                nm = _norm_model(m)
                nt = _norm_model(text)
                if not (nt and (nt in nm or nm in nt)):
                    continue
                specs = r.get("specs") or {}
                if slot == "gpu":
                    return {"gpu": [{"model": m, "qty": int(baseline.get("gpu_slots") or 0) or 1}]}
                if slot == "cpu":
                    return {"cpu": {"model": m, "qty": int(baseline.get("max_cpu") or 0) or 1}}
                cap = _gb_of(specs.get("Capacity"))
                if not cap:
                    continue
                if slot == "memory":
                    return {"memory": {"per_stick_gb": int(cap),
                                       "qty": int(baseline.get("max_dimm") or 0) or 8}}
                media = _drive_media_label({"specs": specs, "model": m})
                item = {"capacity_gb": int(cap), "qty": 1, "media": media or "SSD"}
                return {"drives": [item]}
        return None
    finally:
        repo.close()
