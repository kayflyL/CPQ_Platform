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


def _format_part_candidates(rows, *, detailed: bool, price_ok: bool) -> list:
    """候选行 → 模型视图：part_id/name/match 恒有；price 仅 price_ok 真时出现；
    specs concise=前 8 键值截断 28 字符，detailed=全量。"""
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
    return out


def _part_query_payload(q, *, category: str, keywords: str, offset: int,
                        results: list, mode: str, include_status_rows: bool) -> dict:
    payload = {"ok": True, "mode": mode, "category": category, "keywords": keywords,
               "total": int(q.get("total") or len(results)), "offset": offset,
               "next_offset": q.get("next_offset"),
               "truncated": bool(q.get("truncated")),
               "source": str(q.get("source") or "kp_library/part_query"),
               "note": q.get("note"),
               "spec_keys": q.get("spec_keys") or [],
               "results": results,
               "message": (f"检索到 {len(results)} 条候选"
                           + ("（已截断，可用 required_specs 收窄或 offset 翻页）"
                              if q.get("truncated") else ""))}
    if include_status_rows:
        payload["rows"] = _kp_status_rows()
    return payload


def tool_query_parts(args: dict) -> dict:
    """配件库候选检索（双模式，2026-10-11 流程锁换权限锁）：按类目+结构化规格(required_specs)/关键词查真实库存候选。

    【需求分析流程内=选配模式】数据源走节点 data_bindings（series 随任务机型收窄），
    支持 rows 批量按行召回；落料锁定走 select_parts（仅流程内）。
    【流程外=日常浏览模式】只读检索（series 置空），limit 收窄护上下文；rows 不开放。
    可见性两档门不变：工具挂载看同事 tool_ids 白名单，价格列看 price_ok
    （角色 price_access × 发起用户 RBAC，任一关即无价）。
    offset 分页钻取 + response_format(concise/detailed) 控制返回体量；要看全某个
    **已命中**的料的完整规格用 inspect_parts(action=part)（直接回库读完整规格）。
    """
    args = args or {}
    ctx = TOOL_CTX.get() or {}
    price_ok = bool(ctx.get("price_ok"))
    category = str(args.get("category") or "").strip()
    # ── 日常浏览模式（2026-10-11 定调：流程锁换权限锁）──
    # 流程外=只读检索：KP 库直读（series 置空=不按机型平台收窄），limit 收窄护上下文；
    # 可见性仍由 tool_ids 白名单 × price_ok（角色 price_access × 用户 RBAC）管。
    # rows 批量召回依赖流程行清单，属流程语义不开放；落料锁定 select_parts 仍仅流程内。
    if not ctx.get("task_active"):
        rows_arg = args.get("rows")
        if rows_arg is not None and rows_arg != "":
            return {"ok": False, "error": "rows_only_in_task",
                    "message": "rows 批量召回仅需求分析流程内可用；日常查询请用 category+keywords/required_specs"}
        if not category:
            return {"ok": False, "error": "invalid_args",
                    "message": "category 必填（库内类目，如 Memory/NIC/CPU/SSD/HDD）"}
        keywords = str(args.get("keywords") or "").strip()
        spec_filters = args.get("required_specs")
        if not isinstance(spec_filters, list):
            spec_filters = args.get("spec_filters")
        if not isinstance(spec_filters, list):
            spec_filters = []
        try:
            limit = max(1, min(10, int(args.get("limit") or 6)))
        except (TypeError, ValueError):
            limit = 6
        try:
            offset = max(0, int(args.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        detailed = str(args.get("response_format") or "concise").strip().lower() == "detailed"
        from app.services.part_search import hybrid_search
        q = hybrid_search(category, text=keywords, spec_filters=spec_filters,
                          series="", limit=limit, offset=offset,
                          price_ok=price_ok, mode="query")
        if not q.get("ok"):
            return q
        results = _format_part_candidates(q.get("rows") or [], detailed=detailed, price_ok=price_ok)
        return _part_query_payload(q, category=category, keywords=keywords, offset=offset,
                                   results=results, mode="browse", include_status_rows=False)
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
    save = ctx.get("save")
    if callable(save):
        save()
    results = _format_part_candidates(q.get("rows") or [], detailed=detailed, price_ok=price_ok)
    return _part_query_payload(q, category=category, keywords=keywords, offset=offset,
                               results=results, mode="task", include_status_rows=True)
