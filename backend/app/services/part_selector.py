# -*- coding: utf-8 -*-
"""part_selector —— 需求分析 skill 的唯一配件选型工具（AI 决策，工具落地）。

AI-first 原则：
- AI 决定“要什么/怎么配”：cpu_signal/mem_signal/drive_groups/gpu_groups/raid_groups/
  multi_spec_filters 是唯一真值源（llm_extract_enhance 产出，slot_contract 对齐）。
  AI 在调用 select_parts 前补全模糊项（内存拆条、硬盘接口、GPU 型号等）。
- 工具只做“检索 + 落地”：料号/价格/规格全部来自 KP 库真实返回；未命中白盒 unmatched，
  绝不静默回退固定规则。
- 类目/规则词全部来自 requirement_rule_catalog 与 KP 库，不在代码里写死。
"""
from __future__ import annotations

import re
from typing import Optional

from app.repository.kp_repo import KPRepository


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


def _model_tokens(value) -> list:
    """提取型号里有区分度的 token（含数字的字母数字片段，过滤纯容量词）。

    'NVIDIA RTX PRO 4500 Server 32G' -> ['4500']；'LSI 9560-16i' -> ['9560-16i']。
    这是双向匹配的基础：AI 给的冗长型号与库内短型号也能按 token 对齐。
    """
    toks: list = []
    for m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", str(value or "")):
        t = m.group()
        if not re.search(r"\d", t) or len(t) < 3:
            continue
        if re.match(r"^\d+(?:\.\d+)?[GT]B?$", t, re.I):
            continue
        if t.lower() not in (x.lower() for x in toks):
            toks.append(t)
    return toks


def _model_match(needle, haystack) -> bool:
    """型号对齐：归一化双向包含 或 token 集合互相包含（至少一个非空 token）。

    解决 LLM 输出 'LSI 9560 16i 8G缓存' 或 'RTX PRO 4500 Server 32G' 与库内短型号
    无法按整串子串命中，但 token 同源的情况。
    """
    if not needle or not haystack:
        return False
    nn = _norm_model(needle)
    hn = _norm_model(haystack)
    if nn and hn and (nn in hn or hn in nn):
        return True
    nt = {t.lower() for t in _model_tokens(needle)}
    ht = {t.lower() for t in _model_tokens(haystack)}
    if not nt or not ht:
        return False
    return nt.issubset(ht) or ht.issubset(nt)


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


def _alias_rows(repo, index, term, db_cat=None):
    """语义别名/名称/型号 token 归一 → 库内行列表 + 命中原因（落地层共用）。

    1) 策略中心 part_alias 规则优先（如「兆芯」→ KH40000/KH50000）；
    2) 名称 ILIKE 检索兜底；
    3) 型号 token 归一兜底（长型号 vs 短型号，如 Intel Xeon 6430 → Intel 6430）。
    只返回库内真实行，不静默顶替、不编造料号。
    """
    from app.services.requirement_rule_catalog import part_aliases
    term = str(term or "").strip()
    if not term:
        return [], "缺少术语"
    aliases = part_aliases()
    keys = aliases.get(term) or []
    if keys:
        rows = []
        cats = [db_cat] if db_cat else _search_category_names(repo, index)
        for k in keys:
            for cat in cats:
                rows.extend(repo.get_by_category(cat, search=k))
        return _dedupe_rows(rows), f"别名规则 {term}"
    if db_cat:
        rows = repo.get_by_category(db_cat, search=term)
    else:
        rows = []
        for cat in _search_category_names(repo, index):
            rows.extend(repo.get_by_category(cat, search=term))
    if rows:
        return _dedupe_rows(rows), f"名称搜索 {term}"
    if db_cat:
        hits = [r for r in repo.get_by_category(db_cat)
                if _model_match(term, str(r.get("model") or ""))]
        if hits:
            return _dedupe_rows(hits), f"型号 token 归一 {term}"
    return [], f"名称搜索 {term}"


def resolve_part_alias(term, category=None):
    """语义别名/同义术语 → 库内料号候选（数据驱动 + 名称检索兜底）。

    优先读策略中心 part_alias（如「兆芯」→ KH40000/KH50000）；未命中则按术语
    在指定类目做名称 ILIKE 检索。返回候选 + 命中原因，不静默顶替，不编造料号。
    """
    repo = KPRepository()
    try:
        index = _category_index(repo)
        db_cat = _resolve_db_category(category, index) if category else None
        term = str(term or "").strip()
        rows, reason = _alias_rows(repo, index, term, db_cat)
        out = []
        for r in rows:
            out.append({
                "category": r.get("category") or "",
                "pn": r.get("model") or "",
                "name": r.get("model") or "",
                "unit_price": float(r.get("price") or 0),
                "currency": r.get("currency") or "RMB",
                "reason": reason,
            })
        return {"count": len(out), "candidates": out[:10], "reason": reason}
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
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("cpu")
    search_field = str(policy.get("search_field") or "model")
    qty = int((sig or {}).get("qty") or 1)
    model = str((sig or {}).get(search_field) or "").strip()
    if model:
        index = _category_index(repo)
        rows, reason = _alias_rows(repo, index, model, db_cat)
        rep = pick(rows)
        if not rep:
            return [_unmatched(db_cat, qty, f"库无 {model} CPU 件，未静默顶替")]
        return [_row(db_cat, rep, qty, reason)]
    rows = repo.get_by_category(db_cat)
    rep = pick(rows)
    if not rep:
        return [_unmatched(db_cat, qty, f"库无 {db_cat} 代表件")]
    return [_row(db_cat, rep, qty, "代表件")]


def _ground_memory(repo, db_cat, sig, pick):
    if not isinstance(sig, dict) or not sig:
        return []
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("memory")
    allow_relax = bool(policy.get("allow_speed_relax_without_comparison", False))
    capacity_split = str(policy.get("capacity_split") or "largest_divisor")
    qty = int(sig.get("qty") or 0)
    per = int(sig.get("per_stick_gb") or 0) or None
    total = int(sig.get("total_gb") or 0) or None
    mtype = str(sig.get("type") or "").strip()
    speed = sig.get("speed")
    comparison = str(sig.get("comparison") or "").strip()
    if comparison in ("gte", "lte"):
        speed_op = comparison
    elif allow_relax:
        speed_op = "gte"
    else:
        speed_op = "="
    filters = []
    request_bits = []
    if mtype:
        filters.append({"spec_key": "Type", "op": "=", "value": mtype})
        request_bits.append(mtype)
    if speed:
        filters.append({"spec_key": "Speed", "op": speed_op, "value": speed})
        request_bits.append(f"{speed_op} {speed}")
    else:
        request_bits.append("speed 未给")
    if per:
        request_bits.append(f"{per}G")
    rows = repo.get_by_category_with_specs(db_cat)
    pool = [r for r in rows if _spec_hit(r.get("specs") or {}, filters)] if filters else list(rows)
    if filters and not pool:
        # 规格不满足就白盒未命中，不静默放宽类型/速度（避免 4800 漂成 6400）。
        return [_unmatched(db_cat, qty or 1, f"库无 匹配 {(' '.join(request_bits)).strip() or db_cat} 内存件")]
    if not pool:
        return [_unmatched(db_cat, qty or 1, f"库无 {db_cat} 内存件")]

    def cap_of(r):
        return _gb_of((r.get("specs") or {}).get("Capacity"))

    if per:
        cand = [r for r in pool if cap_of(r) is not None and abs(cap_of(r) - per) < 1e-6]
        if not cand:
            return [_unmatched(db_cat, qty or 1, f"库无 {per}G 单条内存")]
        pool = cand
    elif total:
        caps = sorted({int(c) for c in (cap_of(r) for r in pool if cap_of(r)) if c >= 4})
        chosen = None
        if capacity_split == "largest_divisor":
            chosen = next((c for c in reversed(caps) if total % c == 0), None)
        if chosen:
            per = chosen
            qty = qty or int(total // chosen)
            cand = [r for r in pool if cap_of(r) is not None and abs(cap_of(r) - chosen) < 1e-6]
            pool = cand or pool
    rep = pick(pool)
    if not rep:
        return [_unmatched(db_cat, qty or 1, f"库无 {db_cat} 内存件")]
    matched = _spec_hit(rep.get("specs") or {}, filters)
    if per:
        matched = (matched + " · " if matched else "") + f"容量 {per}G"
    grounded = rep.get("specs") or {}
    gspeed = _num_of(grounded.get("Speed"))
    gtype = str(grounded.get("Type") or "").strip()
    gcap = _gb_of(grounded.get("Capacity"))
    grounded_bits = [b for b in (gtype, (f"{int(gspeed)}" if gspeed is not None else ""),
                                  (f"{int(gcap)}G" if gcap is not None else "")) if b]
    mismatch = False
    if speed is None and gspeed is not None:
        mismatch = True
    elif speed is not None and gspeed is not None:
        if speed_op == "gte":
            mismatch = gspeed < float(speed)
        elif speed_op == "lte":
            mismatch = gspeed > float(speed)
        else:
            mismatch = abs(gspeed - float(speed)) > 1e-9
    return [_row(db_cat, rep, qty or 1, matched,
                 request_spec=" ".join(request_bits).strip(),
                 grounded_spec=" ".join(grounded_bits).strip(),
                 spec_mismatch=mismatch)]


def _ground_drives(repo, db_cat, groups, pick):
    from app.services.requirement_rule_catalog import part_selection_policy
    drive_policy = part_selection_policy("drive")
    tolerance_ratio = float(drive_policy.get("capacity_tolerance_ratio") or 0.05)
    kind_filter = bool(drive_policy.get("kind_filter", True))
    rows = repo.get_by_category_with_specs(db_cat)
    out = []
    for g in groups or []:
        term = str(g.get("term") or g.get("capacity") or "").strip()
        qty = int(g.get("qty") or 1)
        kind = str(g.get("kind") or g.get("interface") or "").strip()
        cmp = str(g.get("comparison") or "").strip()
        need = _gb_of(term)

        def hit(r):
            sp = r.get("specs") or {}
            hay = (str(sp.get("Type") or "") + " " + str(sp.get("Media") or "")).upper()
            if kind_filter and kind and kind.upper() not in hay:
                return False
            if need is None:
                return True
            cap = _gb_of(sp.get("Capacity"))
            if cap is None:
                return False
            if cmp == "gte":
                return cap >= need
            if cmp == "lte":
                return cap <= need
            return abs(cap - need) <= max(1.0, need * tolerance_ratio)

        cand = [r for r in rows if hit(r)]
        rep = pick(cand) if cand else None
        if not rep:
            out.append(_unmatched(db_cat, qty, f"库无 {term or '未知容量'} {kind or '盘'}"))
            continue
        grounded = rep.get("specs") or {}
        gcap = _gb_of(grounded.get("Capacity"))
        gkind = (str(grounded.get("Type") or "") + " " + str(grounded.get("Media") or "")).strip()
        mismatch = False
        if need is not None and gcap is not None:
            if cmp == "gte":
                mismatch = gcap < need
            elif cmp == "lte":
                mismatch = gcap > need
            else:
                mismatch = abs(gcap - need) > max(1.0, need * tolerance_ratio)
        if kind and kind.upper() not in str(grounded.get("Type") or "").upper() + " " + str(grounded.get("Media") or "").upper():
            mismatch = True
        out.append(_row(db_cat, rep, qty, f"{term} {kind}".strip() or "代表件",
                         request_spec=f"{term} {kind}".strip(),
                         grounded_spec=gkind + (f" {int(gcap)}G" if gcap is not None else "").strip(),
                         spec_mismatch=mismatch))
    return out


def _ground_gpu(repo, db_cat, groups, pick):
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("gpu")
    allow_capacity_fallback = bool(policy.get("allow_capacity_fallback_when_model_missing", False))
    check_capacity = bool(policy.get("check_capacity_after_model_match", True))
    tolerance_ratio = float(policy.get("capacity_tolerance_ratio") or 0.05)
    rows = repo.get_by_category_with_specs(db_cat)
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        toks = [t for t in (g.get("tokens") or []) if str(t).strip()]
        cap = g.get("cap")
        cmp = str(g.get("comparison") or "").strip()
        rep = None
        matched = ""
        request_spec = " ".join(str(t).strip() for t in toks)
        requested_cap = _gb_of(cap) if cap is not None else None
        if toks:
            match_tokens = sorted(toks, key=len, reverse=True) if policy.get("match_model_tokens_first", True) else list(toks)
            for tok in match_tokens:
                hits = [r for r in rows if _model_match(tok, r.get("model") or "")]
                if hits:
                    rep = pick(hits)
                    matched = f"型号 {tok}"
                    break
            if rep is None and not allow_capacity_fallback:
                out.append(_unmatched(
                    db_cat, qty,
                    f"库无型号 {request_spec or 'GPU'}；禁止按显存容量静默替换为其他型号"))
                continue
        if rep is None and cap is not None and (not toks or allow_capacity_fallback):
            def gh(r):
                c = _gb_of((r.get("specs") or {}).get("Capacity"))
                return c is not None and not _capacity_mismatch(c, requested_cap, cmp, tolerance_ratio)
            hits = [r for r in rows if gh(r)]
            if hits:
                rep = pick(hits)
                matched = f"显存 {cap}G"
        if rep is None:
            out.append(_unmatched(db_cat, qty, f"库无 {toks[0] if toks else 'GPU'} 件"))
            continue
        grounded = rep.get("specs") or {}
        grounded_cap = _gb_of(grounded.get("Capacity"))
        mismatch = False
        if check_capacity and requested_cap is not None and grounded_cap is not None:
            mismatch = _capacity_mismatch(grounded_cap, requested_cap, cmp, tolerance_ratio)
        grounded_bits = [str(rep.get("model") or "").strip()]
        if grounded_cap is not None:
            grounded_bits.append(f"{int(grounded_cap)}G")
        out.append(_row(db_cat, rep, qty, matched,
                         request_spec=request_spec,
                         grounded_spec=" ".join(grounded_bits).strip(),
                         spec_mismatch=mismatch))
    return out


def _ground_raid(repo, db_cat, groups, pick):
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("raid")
    model_first = bool(policy.get("model_match_first", True))
    require_level = bool(policy.get("require_level_support", True))
    rows = repo.get_by_category_with_specs(db_cat)
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        model = str(g.get("model") or "").strip()
        levels = g.get("raid_levels") or []
        rep = None
        matched = ""
        request_spec = model or ("RAID " + "/".join(str(x) for x in (levels or [])))
        # 模型字段里写了 RAID 级别（如 "RAID 0,1,10"）：这是级别信号，不是卡型号。
        if model and not _model_tokens(model):
            level_scan = re.findall(r"\d+", model)
            levels = [x for x in level_scan if x not in (levels or [])]
            model = ""

        def match_levels():
            nonlocal rep, matched
            level_hits = []
            for r in rows:
                specs = r.get("specs") or {}
                if any(str(level) in str(specs.get(key) or "") for level in levels
                       for key in ("RAID Level", "Raid Level", "Levels", "Supported RAID")):
                    level_hits.append(r)
                    break
            if level_hits:
                rep = pick(level_hits)
                matched = "RAID " + "/".join(str(x) for x in levels)

        if model_first and model:
            hits = [r for r in rows if _model_match(model, r.get("model") or "")]
            if hits:
                rep = pick(hits)
                matched = f"型号 {model}"
        if rep is None and levels:
            match_levels()
            if rep is None and require_level:
                # RAID 级别必须来自目录事实；库内未登记支持级别时不得任取一条代表件。
                out.append(_unmatched(db_cat, qty, f"库内未登记 RAID {'/'.join(str(x) for x in levels)} 支持，无法自动选卡"))
                continue
            if rep is None and not require_level:
                rep = pick(rows)
                matched = "RAID 代表件"
        if rep is None and model and not model_first:
            hits = [r for r in rows if _model_match(model, r.get("model") or "")]
            if hits:
                rep = pick(hits)
                matched = f"型号 {model}"
        if rep is None:
            out.append(_unmatched(db_cat, qty, f"库无 {model or 'RAID'} 件"))
            continue
        out.append(_row(db_cat, rep, qty, matched,
                         request_spec=request_spec,
                         grounded_spec=str(rep.get("model") or "")))
    return out


def _ground_nic(repo, db_cat, msf, pick):
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("nic")
    use_spec_filter = bool(policy.get("spec_filter", True))
    use_name_contains = bool(policy.get("name_contains", True))
    rows = repo.get_by_category_with_specs(db_cat)
    lines = (msf or {}).get("Network(NIC) requirement") or (msf or {}).get(db_cat) or []
    out = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        filters = line.get("filters") or []
        qty = int(line.get("qty") or 1)
        ncontains = line.get("name_contains") or []
        cand = [r for r in rows if _spec_hit(r.get("specs") or {}, filters)] if (use_spec_filter and filters) else list(rows)
        terms = ncontains if isinstance(ncontains, list) else [ncontains]
        terms = [t for t in terms if str(t).strip()]
        if use_name_contains and terms:
            cand = [r for r in cand if all(str(t).strip().lower() in str(r.get("model") or "").lower() for t in terms)]
        rep = pick(cand)
        if not rep:
            out.append(_unmatched(db_cat, qty, "库无匹配网卡"))
            continue
        out.append(_row(db_cat, rep, qty, _spec_hit(rep.get("specs") or {}, filters)))
    return out


def _ground_generic(repo, db_cat, search, qty_map, search_map, pick):
    from app.services.requirement_rule_catalog import part_selection_policy
    policy = part_selection_policy("generic")
    search_field = str(policy.get("search_field") or "keyword")
    qty = int((qty_map or {}).get(db_cat) or 1)
    if search_field == "keyword":
        kw = str((search_map or {}).get(db_cat) or search or "").strip()
    else:
        kw = str(search or "").strip()
    rows = repo.get_latest_prices(search=kw, category=db_cat, sort_by="price", sort_order="asc", include_record_count=False)
    rep = pick(rows)
    if not rep:
        return [_unmatched(db_cat, qty, f"库无 {db_cat} 代表件")]
    return [_row(db_cat, rep, qty, f"关键词 {kw}" if kw else "代表件")]


def select_parts(categories=None, server_type_name=None, search=None, qty_map=None, search_map=None,
                 representative_pick="min_price",
                 cpu_signal=None, mem_signal=None, drive_groups=None,
                 gpu_groups=None, raid_groups=None, psu_signal=None, multi_spec_filters=None):
    """按结构化信号落地真实料号；AI 补全信号（怎么配），工具只检索落地。"""
    pick = lambda rows: _pick(rows, representative_pick)
    repo = KPRepository()
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
        if isinstance(cpu_signal, dict) and cpu_signal:
            _add_cat("CPU")
        if mem_signal:
            _add_cat("Memory")
        if drive_groups:
            _add_cat("HDD/SSD")
        if gpu_groups:
            _add_cat("GPU")
        if raid_groups:
            _add_cat("Raid card")
        if multi_spec_filters:
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
                parts.extend(_ground_cpu(repo, db_cat, cpu_signal, pick))
            elif low == "memory":
                parts.extend(_ground_memory(repo, db_cat, mem_signal, pick))
            elif low in ("hdd/ssd", "ssd", "storage hdd/ssd"):
                parts.extend(_ground_drives(repo, db_cat, drive_groups, pick))
            elif low in ("gpu", "gpu card"):
                parts.extend(_ground_gpu(repo, db_cat, gpu_groups, pick))
            elif "raid" in low or "hba" in low:
                parts.extend(_ground_raid(repo, db_cat, raid_groups, pick))
            elif "nic" in low or "network" in low:
                parts.extend(_ground_nic(repo, db_cat, multi_spec_filters, pick))
            else:
                parts.extend(_ground_generic(repo, db_cat, search, qty_map, search_map, pick))
        return parts
    finally:
        repo.close()
