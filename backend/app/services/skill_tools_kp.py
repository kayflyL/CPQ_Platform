# -*- coding: utf-8 -*-
"""配件检索工具：query_parts（精确通道，直连库）。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
2026-09-11 只读钻取工具迁往 skill_tools_open.py；2026-09-12 收敛为统一入口 inspect_parts(action=...)。
"""
from __future__ import annotations

import re

from app.services.skill_memory import _kp_status_rows
from app.services.skill_node_state import KP_PICKS, KP_RECOMMEND, kp_state
from app.services.skill_tool_context import TOOL_CTX

def _zero_reason(cat: str, q: dict) -> str:
    """行召回零命中时的接地提示：把该类目真实 specs 字段交给模型，引导它改数值/型号词或 spec_filter，而非全类目浏览。

    「零命中」有两种：确实库里没有；库里有但被机型平台适配挡在门外（q.scope_note 已把
    被挡住的料与适配平台列出来）。后者不许说成前者——说错了客户就只能听 AI 编替代方案。
    """
    if q.get("scope_note"):
        return str(q["scope_note"])
    _sk = q.get("spec_keys") or []
    return ("库内无精确匹配（行描述召回零命中）；该类目 specs 字段："
            + ("、".join(str(s) for s in _sk[:8]) if _sk else "（无结构规格）")
            + "。可对该类目用 category+关键词（数值/型号词）或 required_specs 的库内字段收窄重查")


def _search_kp_parts_by_rows(rows_arg, *, limit, detailed, price_ok, ctx) -> dict:
    """批量按行召回候选（2026-09-09 提速）：一次覆盖多行，每行用自己的类目+行描述去配件库召回，
    返回每行的紧凑候选视图。progressive disclosure 不变——只回各行命中的候选，
    AI 仍看着候选选料，不自动代选；零召回行明示原因，不退化类目全量。
    """
    from app.services.part_search import hybrid_search
    rows_ctx = [r for r in (ctx.get("kp_rows_ctx") or []) if isinstance(r, dict)]
    if not rows_ctx:
        return {"ok": False, "error": "no_unmatched_rows",
                "message": "没有待选型配件行（行清单为空）"}
    _st = kp_state(ctx.get("engine") or {})
    _picks = _st.get(KP_PICKS) if isinstance(_st.get(KP_PICKS), dict) else {}
    _recs = _st.get(KP_RECOMMEND) if isinstance(_st.get(KP_RECOMMEND), dict) else {}

    def _is_pending(r: dict) -> bool:
        rk = str(r.get("row_key") or "")
        return bool(rk) and rk not in _picks and rk not in _recs

    if isinstance(rows_arg, (list, tuple)):
        want = {str(w).strip() for w in rows_arg if str(w).strip()}
    else:
        want = set() if str(rows_arg).strip().lower() in ("all", "*", "") else {str(rows_arg).strip()}
    if not want or "all" in want:
        targets = [r for r in rows_ctx if _is_pending(r)]
    else:
        targets = [r for r in rows_ctx
                   if str(r.get("row_id") or "") in want or str(r.get("row_key") or "") in want]
    if not targets:
        return {"ok": False, "error": "invalid_rows",
                "message": "rows 里没有匹配的待选型行（行清单里没有这些 row_id）"}
    series = str(ctx.get("kp_series") or "")
    batch = []
    for r in targets:
        cat = str(r.get("category") or "").strip()
        desc = str(r.get("description") or "").strip() or cat
        # 客户对该行的补充回答只影响「检索文本」，行键仍取自登记原文（上游冻结文档只读）
        search_desc = (desc + " " + str(r.get("answer") or "")).strip()
        q = hybrid_search(cat, text=search_desc, series=series, limit=limit,
                          price_ok=price_ok, mode="recall")
        cands = []
        for c in (q.get("rows") or []) if q.get("ok") else []:
            if not isinstance(c, dict) or not str(c.get("name") or "").strip():
                continue
            o = {"part_id": c.get("part_id"), "name": c.get("name")}
            if c.get("match"):
                o["match"] = c.get("match")
            if price_ok and c.get("price") is not None:
                o["price"] = c.get("price")
            specs = c.get("specs") if isinstance(c.get("specs"), dict) else {}
            if specs:
                if detailed:
                    o["specs"] = specs
                else:
                    o["specs"] = {str(k): str(v)[:28] for k, v in list(specs.items())[:8]
                                  if str(v or "").strip()}
            cands.append(o)
        batch_row = {
            "row_id": r.get("row_id"), "row_key": r.get("row_key"),
            "category": cat, "description": desc,
            "qty": int(r.get("qty") or 1) if r.get("qty") is not None else 1,
            "specified": bool(r.get("specified")),
            "candidates": cands, "total": int(q.get("total") or len(cands)),
            "truncated": bool(q.get("truncated")),
            "reason": ("" if cands else (_zero_reason(cat, q))),
        }
        if not cands and q.get("out_of_scope"):
            batch_row["out_of_scope"] = q.get("out_of_scope")
        batch.append(batch_row)
    save = ctx.get("save")
    if callable(save):
        save()
    return {"ok": True, "mode": "row_batch",
            "batch": batch, "rows": _kp_status_rows(),
            "message": (f"已按行召回 {len(batch)} 行候选" +
                        ("；其中部分行零召回，请对零召回行用 category 单查收窄"
                         if any(not b["candidates"] for b in batch) else ""))}


def tool_query_parts(args: dict) -> dict:
    """【需求分析流程工具】kp_reason 配件选配回合专用：按类目+结构化规格(required_specs)/关键词检索配件库真实候选。

    progressive disclosure（2026-09-06）+ 统一数据层：大脑不再吃候选池快照，逐行按需
    query。支持 required_specs（结构化规格过滤，AND）与 keywords；结果就是库里的真实行，
    直接在返回里交给大脑比对——同一类目下多条需求行（480G SSD / 6T HDD / 1.92T SSD）
    各查各的，落料时按料号名回库核对。数据源走节点 data_bindings。
    offset 分页钻取 + response_format(concise/detailed) 控制返回体量：截断时 AI 可翻页或
    加 required_specs 收窄，把排在后段的料也捞上来。要看全某个**已命中**的料的规格用
    inspect_parts(action=part)（直接回库读完整规格）。rows 模式：按行批量有界召回（每行用
    自己的类目+行描述），AI 主动发起，不做服务端预取。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "query_parts 仅在需求分析流程的配件选配环节可用"}
    category = str((args or {}).get("category") or "").strip()
    rows_arg = (args or {}).get("rows")
    if not category and rows_arg is not None and rows_arg != "":
        try:
            _lim = max(1, min(20, int((args or {}).get("limit") or 6)))
        except (TypeError, ValueError):
            _lim = 6
        _det = str((args or {}).get("response_format") or "concise").strip().lower() == "detailed"
        return _search_kp_parts_by_rows(rows_arg, limit=_lim, detailed=_det,
                                        price_ok=bool(ctx.get("price_ok")), ctx=ctx)
    if not category:
        return {"ok": False, "error": "invalid_args",
                "message": "category 必填（库内类目，如 Memory/NIC/CPU；可用 search 前先看行清单）"}
    keywords = str((args or {}).get("keywords") or "").strip()
    spec_filters = (args or {}).get("required_specs")
    if not isinstance(spec_filters, list):
        spec_filters = (args or {}).get("spec_filters")
    if not isinstance(spec_filters, list):
        spec_filters = []
    try:
        limit = max(1, min(20, int((args or {}).get("limit") or 8)))
    except (TypeError, ValueError):
        limit = 8
    try:
        offset = max(0, int((args or {}).get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    detailed = str((args or {}).get("response_format") or "concise").strip().lower() == "detailed"
    from app.services.part_search import hybrid_search
    q = hybrid_search(category, text=keywords, spec_filters=spec_filters,
                      series=str(ctx.get("kp_series") or ""), limit=limit, offset=offset,
                      price_ok=bool(ctx.get("price_ok")), mode="query")
    if not q.get("ok"):
        return q
    rows = q.get("rows") or []
    price_ok = bool(ctx.get("price_ok"))
    save = ctx.get("save")
    if callable(save):
        save()
    out = []
    for c in rows:
        o = {"part_id": c.get("part_id"), "name": c.get("name")}
        if c.get("match"):
            o["match"] = c.get("match")
        if price_ok and c.get("price") is not None:
            o["price"] = c.get("price")
        specs = c.get("specs") if isinstance(c.get("specs"), dict) else {}
        if specs:
            if detailed:
                o["specs"] = specs
            else:
                o["specs"] = {str(k): str(v)[:28] for k, v in list(specs.items())[:8]
                              if str(v or "").strip()}
        out.append(o)
    return {"ok": True, "category": category, "keywords": keywords,
            "total": int(q.get("total") or len(out)), "offset": offset,
            "next_offset": q.get("next_offset"),
            "truncated": bool(q.get("truncated")),
            "source": str(q.get("source") or "kp_library/part_query"),
            "note": q.get("note"),
            "spec_keys": q.get("spec_keys") or [],
            "results": out,
            "rows": _kp_status_rows(),
            "message": (f"检索到 {len(out)} 条候选" +
                        "（已截断，可用 required_specs 收窄或 offset 翻页）" if q.get("truncated")
                        else f"检索到 {len(out)} 条候选")}
