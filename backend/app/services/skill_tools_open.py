# -*- coding: utf-8 -*-
"""配件只读钻取工具：统一入口 inspect_parts（action=part/row/category/grep）。

2026-09-11 自 skill_tools_kp.py 拆出（纯搬运，零行为变更）。

与 skill_tools_kp 的分工：那边是**检索**（query_parts 去库取候选）；这边是**只读钻取**
（看单件/单行/类目剖面/结果集内 grep）——只读库，不写任何状态、不留任何台账。
命中后要落地，回 skill_tools_select.select_parts（落料时按料号名回库核对）。
"""
from __future__ import annotations

import re

from app.services.part_selector import pick_for_row, pick_is_stale
from app.services.skill_memory import _kp_status_rows
from app.services.skill_node_state import KP_PICKS, KP_RECOMMEND, kp_state
from app.services.skill_tool_context import TOOL_CTX


def _brief_specs(specs, n: int = 6) -> dict:
    return {str(k): str(v)[:28] for k, v in list((specs or {}).items())[:n]
            if str(v or "").strip()}


def tool_open_part(args: dict) -> dict:
    """【任务期工具】open_part：打开一颗料，读它的完整规格（直接回库读，不靠留底）。

    query_parts 的 concise 候选只带前 8 个规格键、值截 28 字符，要点开细看时用本工具。
    name（料号名，可带 category 收窄）或 part_id（库内行号）都能打开；库里没有就如实说没有。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "inspect_parts(action=\"part\") 仅在任务期的配件选配环节可用"}
    a = args or {}
    part_id = str(a.get("part_id") or "").strip()
    name = str(a.get("name") or "").strip()
    cat_arg = str(a.get("category") or "").strip()
    if not part_id and not name:
        return {"ok": False, "error": "invalid_args",
                "message": "name（料号名）或 part_id 至少给一个"}
    price_ok = bool(ctx.get("price_ok"))
    from app.services.part_selector import KPRepository, _category_index
    repo = KPRepository()
    try:
        matched: list = []
        if name:
            from app.services.data_tools import lookup_parts_by_name
            cats = ([cat_arg] if cat_arg else
                    [str(e["db_category"]) for e in _category_index(repo)["by_key"].values()])
            for c in cats:
                lk = lookup_parts_by_name(c, name, _repo=repo, price_ok=price_ok)
                if not lk.get("ok"):
                    return {"ok": False,
                            "error": str(lk.get("error") or "unknown_category"),
                            "message": str(lk.get("message") or "")}
                for hit_row in (lk.get("rows") or []):
                    if isinstance(hit_row, dict):
                        matched.append({**hit_row, "category": str(c)})
        else:
            from app.services.data_tools import lookup_part_by_id
            lk = lookup_part_by_id(part_id, _repo=repo, price_ok=price_ok)
            matched = [r for r in (lk.get("rows") or []) if isinstance(r, dict)]
        if not matched:
            return {"ok": False, "error": "no_such_part",
                    "message": (f"库里没有这个料号：{name or part_id}"
                                "（先 inspect_parts(action=\"grep\") 定位，或 query_parts 看该类目有哪些料）")}
        if len(matched) > 1 and not cat_arg:
            return {"ok": False, "error": "ambiguous_part",
                    "candidates": [{"category": m.get("category"), "name": m.get("name")}
                                   for m in matched[:8]],
                    "message": (f"库内同名料号有 {len(matched)} 颗："
                                "把 category 一起传进来就能打开指定那颗")}
        ent = matched[0]
        specs = ent.get("specs") if isinstance(ent.get("specs"), dict) else {}
        out = {"ok": True, "category": str(ent.get("category") or cat_arg),
               "part_id": str(ent.get("part_id") or ""),
               "name": str(ent.get("name") or ""),
               "currency": str(ent.get("currency") or "RMB"),
               "specs": dict(specs), "spec_count": len(specs)}
        if price_ok and ent.get("price") is not None:
            out["price"] = ent.get("price")
        out["message"] = (f"已打开 {out['name']} 的完整规格（直接回库读）" if specs else
                          f"已打开 {out['name']}；该类目无结构规格字段，只能按型号名判断")
        return out
    finally:
        repo.close()


def tool_open_row(args: dict) -> dict:
    """【任务期工具】open_row：打开一行**待选型行**，回它的状态、库内候选与未决原因。

    与 _kp_status_rows 的行状态回传互补：那份只给 row_id/类目/结局（紧凑，每次工具调用都带）；
    这里给**单行**的决策上下文——描述/数量/客户是否写明/当前结局/库内按该行描述召回的候选。
    行清单本身已在上下文里，本工具不重发全清单，只回点名的那一行。零状态写入。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "inspect_parts(action=\"row\") 仅在任务期的配件选配环节可用"}
    a = args or {}
    rid = str(a.get("row_id") or "").strip()
    rk_arg = str(a.get("row") or "").strip()
    if not rid and not rk_arg:
        return {"ok": False, "error": "invalid_args",
                "message": "row_id 或 row 必填（用行清单里给出的 row_id 原文）"}
    rows = [r for r in (ctx.get("kp_rows_ctx") or []) if isinstance(r, dict)]
    if not rows:
        return {"ok": False, "error": "no_unmatched_rows",
                "message": "没有待选型配件行（行清单为空）"}
    hit = None
    for r in rows:
        if rid and str(r.get("row_id") or "") == rid:
            hit = r
            break
        if rk_arg and str(r.get("row_key") or "") == rk_arg:
            hit = r
            break
    if hit is None:
        return {"ok": False, "error": "row_unknown",
                "available": [{"row_id": r.get("row_id"), "category": r.get("category"),
                               "description": r.get("description")} for r in rows][:20],
                "message": ("row_id 不在待选型行清单内（见 available，用清单里的原文）。"
                            "已锁定/已豁免的行不在待选型清单里。")}
    cat = str(hit.get("category") or "").strip()
    row_key = str(hit.get("row_key") or "")
    st = kp_state(ctx.get("engine") or {})
    picks = st.get(KP_PICKS) if isinstance(st.get(KP_PICKS), dict) else {}
    recs = st.get(KP_RECOMMEND) if isinstance(st.get(KP_RECOMMEND), dict) else {}
    _desc = str(hit.get("description") or "")
    status, landed = "待处理", ""
    # P3-2：pick/推荐按行身份解析（键是 row_id，条目自带 category/description/rev）。
    pk = pick_for_row(picks, cat, _desc, row=hit)
    rec = pick_for_row(recs, cat, _desc, row=hit)
    rec = rec[0] if isinstance(rec, list) and rec else rec
    _pk_first = pk[0] if isinstance(pk, list) and pk else pk
    if isinstance(_pk_first, dict) and not pick_is_stale(_pk_first, cat, _desc):
        items = [i for i in (pk if isinstance(pk, list) else [pk]) if isinstance(i, dict)]
        status = "已锁定"
        landed = "+".join(str(i.get("name") or "") for i in items if str(i.get("name") or ""))
    elif isinstance(rec, dict) and not pick_is_stale(rec, cat, _desc):
        status = "推荐待确认"
        landed = str(rec.get("name") or "")
    # 库内候选：实时按行描述回库召回（2026-09-12 去台账——不再是「本轮检索留底」的索引）
    cands: list = []
    if status == "待处理" and cat:
        from app.services.data_tools import part_recall
        _q = part_recall(cat, desc=(_desc + " " + str(hit.get("answer") or "")).strip(),
                         series=str(ctx.get("kp_series") or ""), limit=12,
                         price_ok=bool(ctx.get("price_ok")))
        for ent in ((_q.get("rows") or []) if _q.get("ok") else []):
            if not isinstance(ent, dict):
                continue
            o = {"part_id": ent.get("part_id"), "name": ent.get("name")}
            if ctx.get("price_ok") and ent.get("price") is not None:
                o["price"] = ent.get("price")
            sp = ent.get("specs") if isinstance(ent.get("specs"), dict) else {}
            if sp:
                o["specs_brief"] = _brief_specs(sp)
            cands.append(o)
    out = {"ok": True, "row_id": hit.get("row_id"), "row_key": row_key,
           "category": cat, "description": hit.get("description"),
           "qty": hit.get("qty") or 1, "status": status,
           "specified": bool(hit.get("specified")),
           "candidate_count": len(cands),
           "candidates": cands[:12]}
    if hit.get("answer"):
        out["answer"] = hit.get("answer")
    if landed:
        out["part"] = landed
    if status == "已锁定":
        out["message"] = f"该行已锁定（{landed or '已锁定'}）"
    elif not cands:
        out["message"] = f"类目 {cat}：库内按该行描述召回零命中"
    else:
        out["message"] = f"类目 {cat}：库内按该行描述召回 {len(cands)} 颗候选（实时查库，上面是紧凑视图）"
    return out


_VAL_NUM_RE = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*[A-Za-z%]{0,6}\s*$")


def _spec_profile(rows: list, *, max_keys: int = 12, max_values: int = 5) -> tuple:
    """类目 specs 字段画像：字段 → 出现件数 / 去重取值数 / 取值样例 / 粗略种类（numeric|text）。

    只做确定性统计与截断，不做语义归一（值原样返回）。按出现件数降序排，截到 max_keys。
    返回 (profiles, all_keys)。
    """
    agg: dict = {}
    for r in rows:
        sp = r.get("specs") if isinstance(r.get("specs"), dict) else {}
        for k, v in sp.items():
            kk = str(k or "").strip()
            sv = str(v if v is not None else "").strip()
            if not kk or not sv:
                continue
            e = agg.setdefault(kk, {"key": kk, "parts": 0, "seen": set(), "values": []})
            e["parts"] += 1
            if sv in e["seen"]:
                continue
            e["seen"].add(sv)
            if len(e["values"]) < max_values:
                e["values"].append(sv[:28])
    prof: list = []
    for e in agg.values():
        vals = e["values"]
        numeric = sum(1 for v in vals if _VAL_NUM_RE.match(v))
        prof.append({"key": e["key"], "parts": e["parts"], "distinct": len(e["seen"]),
                     "values": vals,
                     "kind": ("numeric" if vals and numeric * 2 >= len(vals) else "text")})
    prof.sort(key=lambda x: (-x["parts"], x["key"]))
    return prof[:max_keys], sorted(agg.keys())


def tool_open_category(args: dict) -> dict:
    """【任务期工具】open_category：打开一个**类目**的「目录页」——库内叫什么、多少件、有哪些 specs
    字段（各出现多少件、取值样例、是数值还是文本）、价格区间、几颗料名样例（认命名习惯用）、
    以及下一步怎么检索。**只读：零写入**——本页返回的料名仅供认路、不是候选；
    要锁定按返回的下一步去检索，再用 select_parts 按料号名落行。

    与 query_parts 的分工：query_parts 要你先知道要查哪个字段、什么值；open_category 用来看
    「这个类目里有什么字段、值长什么样」，把猜字段变成看字段。category 支持中文别名（网卡→NIC）。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "inspect_parts(action=\"category\") 仅在任务期的配件选配环节可用"}
    cat = str((args or {}).get("category") or "").strip()
    from app.services.part_selector import (KPRepository, _category_index,
                                            _resolve_db_category, _series_ok)
    repo = KPRepository()
    try:
        index = _category_index(repo)

        def _avail() -> list:
            a = [{"category": e["db_category"], "parts": e["count"],
                  "aliases": e.get("aliases") or []} for e in index["by_key"].values()]
            a.sort(key=lambda x: (-x["parts"], x["category"]))
            return a

        if not cat:
            return {"ok": False, "error": "invalid_args", "categories": _avail(),
                    "message": ("category 必填；上面是库内真实类目（含中文别名），"
                                "传其一即可打开该类目目录页")}
        db_cat = _resolve_db_category(cat, index)
        if not db_cat:
            return {"ok": False, "error": "unknown_category", "categories": _avail(),
                    "message": f"类目 {cat} 不在配件库；见 categories 里的真实类目名与别名"}
        rows = repo.get_by_category_with_specs(db_cat) or []
        price_ok = bool(ctx.get("price_ok"))
        series = str(ctx.get("kp_series") or "").strip()
        prof, all_keys = _spec_profile(rows)
        _lower = {str(k).lower(): e for k, e in index["by_key"].items()}
        out = {"ok": True, "mode": "category", "category": cat, "db_category": db_cat,
               "aliases": list((_lower.get(db_cat.lower()) or {}).get("aliases") or []),
               "parts_in_library": len(rows),
               "spec_fields": prof, "spec_field_count": len(all_keys)}
        if len(all_keys) > len(prof):
            out["spec_fields_omitted"] = len(all_keys) - len(prof)
        if price_ok:
            prices = [float(r.get("price") or 0) for r in rows if r.get("price")]
            if prices:
                out["price_range"] = {
                    "min": min(prices), "max": max(prices),
                    "currency": str(rows[0].get("currency") or "RMB")}
        names = [str(r.get("model") or "") for r in rows if str(r.get("model") or "").strip()]
        if names:
            out["example_names"] = names[:5]
        if series:
            in_series = sum(1 for r in rows
                            if _series_ok(r.get("applicable"), series))
            out["series"] = series
            out["parts_in_series"] = in_series
            if not in_series:
                out["note"] = (f"适配当前平台 {series} 的件数：0（库内共 {len(rows)} 件，"
                               f"「库内件数」与「适配件数」是两回事）。")
        nk = "、".join(p["key"] for p in prof[:8]) or "（该类目无结构规格）"
        out["message"] = (
            f"类目 {db_cat}：库内 {len(rows)} 件，specs 字段 {len(all_keys)} 个（{nk}）。"
            "本页只描述类目结构、**不登记任何候选**（example_names 仅供认命名习惯）。")
        return out
    finally:
        repo.close()


def _grep_hit(pattern: str, regex: bool = False):
    """构造匹配器：返回 (hit(text)->命中的字面片段或 None, 标签)。

    非正则：pattern 按空白或 | 切成多个词，任一命中即算命中（大小写不敏感子串）。
    正则：re.I 搜索，回匹配到的原文片段。都不做语义等价（10G 不会命中 万兆）。
    """
    p = str(pattern or "").strip()
    if not p:
        return (lambda _t: None), ""
    if regex:
        rx = re.compile(p, re.I)

        def _rx_hit(t: str):
            m = rx.search(t)
            return m.group(0) if m else None
        return _rx_hit, f"regex:{p}"
    terms = [t for t in re.split(r"[\s|]+", p) if t]
    low = [t.lower() for t in terms]

    def _lit_hit(t: str):
        tl = str(t).lower()
        for raw, lo in zip(terms, low):
            if lo in tl:
                return raw
        return None
    return _lit_hit, "|".join(terms)


def _snippet(text: str, frag: str, *, pad: int = 24, cap: int = 80) -> str:
    """命中片段的前后文（给模型看值长什么样），超出部分用省略号收口。"""
    s = str(text or "")
    if not frag:
        return s[:cap]
    i = s.lower().find(str(frag).lower())
    if i < 0:
        return s[:cap]
    a = max(0, i - pad)
    b = min(len(s), i + len(frag) + pad)
    return ("…" if a > 0 else "") + s[a:b] + ("…" if b < len(s) else "")


def tool_grep_parts(args: dict) -> dict:
    """【任务期工具】grep_parts：在配件库里**字面/正则搜索**——扫每颗件的名称与 specs 取值，
    回「哪个类目、哪颗料、哪个字段、命中了什么」，用于按型号/编码/接口词找料（9361、CX6、NVMe）。

    与 query_parts 的分工：query_parts 是「按类目+规格过滤取候选」；grep 是「拿一个词扫全库，
    看它出现在哪」。三级检索的最后一层：先 open_category 看字段（navigate），词不知道在哪个
    字段时用 grep，锁定前仍须 query_parts。

    category 缺省时扫遍库内全部类目；命中按 offset/limit 分页（total=真实命中件数）。
    **只读：零写入**——matches 里的料不是候选，select_parts 不认；
    要锁定用 suggest_next 里的 parameters 去调 query_parts，或自己带 keywords 收窄。
    series 已锁定时每条命中会标 in_scope（适配当前平台否），不适配的照样返回、如实标注。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "inspect_parts(action=\"grep\") 仅在任务期的配件选配环节可用"}
    a = args or {}
    pattern = str(a.get("pattern") or "").strip()
    if not pattern:
        return {"ok": False, "error": "invalid_args",
                "message": ("pattern 必填（要搜的字面串，如 9361 / CX6 / NVMe；"
                            "多个词用空白或 | 分隔 = 任一命中）")}
    regex = bool(a.get("regex"))
    try:
        hit, label = _grep_hit(pattern, regex)
    except re.error as exc:
        return {"ok": False, "error": "invalid_args",
                "message": f"正则不合法：{exc}（改字面串或修正 regex）"}
    fields = str(a.get("fields") or "both").strip().lower()
    if fields not in ("both", "name", "specs"):
        fields = "both"
    spec_key = str(a.get("spec_key") or "").strip()
    try:
        limit = max(1, min(100, int(a.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = max(0, int(a.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    from app.services.part_selector import (KPRepository, _category_index,
                                            _resolve_db_category, _series_ok)
    cat = str(a.get("category") or "").strip()
    repo = KPRepository()
    try:
        index = _category_index(repo)
        if cat:
            db_cat = _resolve_db_category(cat, index)
            if not db_cat:
                avail = sorted(str(e["db_category"]) for e in index["by_key"].values())
                return {"ok": False, "error": "unknown_category", "categories": avail,
                        "message": f"类目 {cat} 不在配件库；见 categories，或省略 category 扫全库"}
            cats = [db_cat]
        else:
            cats = [str(e["db_category"]) for e in index["by_key"].values()]
        series = str(ctx.get("kp_series") or "").strip()
        matches: list = []
        scanned = 0
        cat_hits: dict = {}
        for c in cats:
            for r in repo.get_by_category_with_specs(c) or []:
                scanned += 1
                hits: list = []
                if fields in ("both", "name"):
                    name = str(r.get("model") or "")
                    frag = hit(name)
                    if frag:
                        hits.append({"field": "name", "match": frag,
                                     "value": _snippet(name, frag)})
                if fields in ("both", "specs"):
                    sp = r.get("specs") if isinstance(r.get("specs"), dict) else {}
                    for k, v in sp.items():
                        kk = str(k or "")
                        if spec_key and kk.lower() != spec_key.lower():
                            continue
                        sv = str(v if v is not None else "")
                        frag = hit(sv)
                        if frag:
                            hits.append({"field": kk or "(未命名字段)", "match": frag,
                                         "value": _snippet(sv, frag)})
                if not hits:
                    continue
                cat_hits[c] = cat_hits.get(c, 0) + 1
                m = {"category": c, "part_id": str(r.get("id") or ""),
                     "name": str(r.get("model") or ""), "hits": hits[:5]}
                if series:
                    m["in_scope"] = bool(_series_ok(r.get("applicable"), series))
                matches.append(m)
    finally:
        repo.close()
    total = len(matches)
    page = matches[offset:offset + limit]
    more = total > offset + len(page)
    res = {"ok": True, "mode": "grep", "pattern": pattern, "regex": regex,
           "fields": fields, "spec_key": (spec_key or None), "label": label,
           "categories_scanned": len(cats), "parts_scanned": scanned,
           "total": total, "offset": offset,
           "next_offset": (offset + len(page) if more else None),
           "truncated": more, "matched_categories": cat_hits, "matches": page}
    if total:
        top = max(cat_hits.items(), key=lambda kv: (kv[1], kv[0]))[0]
        kw = page[0]["hits"][0]["match"] if page and page[0]["hits"] else pattern
        res["suggest_next"] = {"tool": "query_parts",
                               "parameters": {"category": top, "keywords": kw}}
        res["message"] = (
            f"grep「{label}」扫 {len(cats)} 类目 / {scanned} 件，命中 {total} 件"
            f"（分布 {cat_hits}）。本工具只报「在哪命中」，**不登记候选**。")
    else:
        res["message"] = (
            f"grep「{label}」扫 {len(cats)} 类目 / {scanned} 件，零命中。"
            "本工具是字面/正则匹配、不做语义等价（10G 不会命中 万兆、大显存不会命中 80G）——"
            "零命中即字面无命中，不代表库里没有语义等价物。")
    return res


def tool_inspect_parts(args: dict) -> dict:
    """统一只读钻取入口：一个工具收敛 part/row/category/grep 四种只读动作。

    该函数只做 action 分发，业务语义仍由 tool_open_part / tool_open_row /
    tool_open_category / tool_grep_parts 四个内部函数承载（插头不变、工具面收敛）。
    """
    action = str((args or {}).get("action") or "").strip().lower()
    if action == "part":
        return tool_open_part(args or {})
    if action == "row":
        return tool_open_row(args or {})
    if action == "category":
        return tool_open_category(args or {})
    if action == "grep":
        return tool_grep_parts(args or {})
    return {"ok": False, "error": "invalid_args",
            "message": "action 必填：part（看单件）/ row（看单行）/ category（看类目）/ grep（扫全库）"}
