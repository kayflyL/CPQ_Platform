# -*- coding: utf-8 -*-
"""通识工具：catalog_search（在售目录）、query_data（边界内只读取数）、ask_user（升格选项卡）。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

import logging
from app.services.skill_tool_context import TOOL_CTX


logger = logging.getLogger(__name__)


def tool_catalog_search(args: dict) -> dict:
    """在售目录查询（推荐的事实来源）：types=类型清单；models=按类型/系列/形态查机型（含价格）。

    无任何过滤条件的 models 查询=浏览全目录（角色推荐场景的合法动作），
    按类型逐个取再合并；引擎的「无信号返空」守卫只属于选型，不拦目录浏览。
    """
    kind = str((args or {}).get("kind") or "models").strip()
    limit = int((args or {}).get("limit") or 8)
    try:
        if kind == "meta":
            # 轻量目录元信息：一次返回 类型/系列/形态 三个候选清单，
            # 供 agent_fill 对「服务器类型/平台类型/机箱形态」做初判，不塞全目录进上下文。
            from app.services.catalog_options import catalog_whitelist
            wl = catalog_whitelist()
            return {"ok": True, "types": wl.get("types") or [],
                    "series": wl.get("series") or [], "forms": wl.get("forms") or []}
        if kind == "types":
            from app.repository.server_catalog_repo import ServerCatalogRepository
            return {"ok": True, "types": [t.get("name") for t in ServerCatalogRepository().list_types() if t.get("name")]}
        if kind == "parts":
            # 配件目录（角色「有什么配件可选」的事实来源）：按品类+系列适配过滤，
            # 与引擎落地同一 applicable 语义，推荐给客户的件必然装得上。
            cat = str((args or {}).get("category") or "").strip()
            p_series = str((args or {}).get("series") or "").strip()
            if not cat:
                from app.services.part_selector import list_kp_categories
                return {"ok": True, "categories": list_kp_categories(),
                        "hint": "先按 category=品类 查询，可选 series 过滤适配平台"}
            from app.repository.kp_repo import KPRepository
            from app.services.part_selector import _series_ok
            _repo = KPRepository()
            try:
                rows = _repo.get_by_category_with_specs(cat)
            finally:
                _repo.close()
            if p_series:
                rows = [r for r in rows if _series_ok(r.get("applicable"), p_series)]
            pout = []
            price_ok = bool(TOOL_CTX.get().get("price_ok", True))
            for r in rows[:max(1, min(limit, 12))]:
                item = {"name": r.get("model"), "category": cat,
                        "applicable_series": (r.get("applicable") or {}).get("series")
                        if isinstance(r.get("applicable"), dict) else None}
                if price_ok:
                    try:
                        if float(r.get("price") or 0) > 0:
                            item["price"] = float(r.get("price"))
                    except (TypeError, ValueError):
                        pass
                pout.append(item)
            return {"ok": True, "parts": pout}
        from app.services.model_candidates import select_models
        type_name = str((args or {}).get("type_name") or "").strip() or None
        series = str((args or {}).get("series") or "").strip() or None
        form = str((args or {}).get("form") or "").strip() or None
        rows: list = []
        if not any([type_name, series, form]):
            from app.repository.server_catalog_repo import ServerCatalogRepository
            for t in ServerCatalogRepository().list_types():
                if len(rows) >= limit:
                    break
                rows.extend(select_models(usage=None, server_type_name=str(t.get("name") or "").strip() or None, limit=limit) or [])
        else:
            rows = select_models(usage=None, server_type_name=type_name, series=series, form=form, limit=limit) or []
        out = []
        price_ok = bool(TOOL_CTX.get().get("price_ok", True))
        for r in rows[:max(1, min(limit, 12))]:
            item = {"name": r.get("name"), "type": r.get("server_type_name"), "series": r.get("series"),
                    "form": r.get("form")}
            if price_ok:
                item["price"] = r.get("total_price")
            out.append(item)
        return {"ok": True, "models": out}
    except Exception as exc:
        logger.exception("catalog_search 失败")
        return {"ok": False, "error": str(exc)}


def tool_query_data(args: dict) -> dict:
    """query_data：数据边界内的只读 SELECT 原语（2026-08-29 步骤2）。

    权限全部在 execute_read（物理校验+只读事务+超时+行数上限+列脱敏）；
    这里只做上下文接线与审计。SQL 报错原样回传，模型据此自纠。
    """
    ctx = TOOL_CTX.get()
    boundary = ctx.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("mode") != "allow_read":
        return {"ok": False, "error": "数据边界为拒绝模式（deny_all），无读取权限"}
    sql = str((args or {}).get("sql") or "").strip()
    if not sql:
        return {"ok": False, "error": "缺 sql 参数（单条只读 SELECT）"}
    try:
        limit = int((args or {}).get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    from app.services.data_boundary import execute_read
    out = execute_read(sql, boundary, limit=limit)
    logger.info("query_data role=%s ok=%s rows=%s truncated=%s sql=%s",
                ctx.get("role_key") or "?", bool(out.get("ok")),
                out.get("row_count") or 0, bool(out.get("truncated")),
                " ".join(sql.split())[:300])
    return out


def tool_ask_user(args: dict) -> dict:
    """【任务期工具】大脑回合专用：把需要客户决策的问题升格为结构化选项卡。

    大脑的自由文本提问只能到达聊天区、没有交互通道（2026-09-05 用户实测：锁 4 行后
    问「1.92T 需确认接口」但没有任何可点的卡）。此工具把问题+选项登记进回合上下文，
    由 skill_chat 在引擎结束后统一弹卡；点击走 (slot,value) 留底匹配。row 绑定行键时，
    选项带 pick → 客户点选即落地该料号；不带 pick → 答案记进该行的补充回答（登记表不动），
    供下一轮据此再选。
    一回合一卡（与缺口卡的单焦点序列同口径）：已有待答问题再调即拒绝。
    行引用收口（2026-09-11 P2，P3-3 收紧）：行清单在场时 row 必须是清单里的 row_id 原文
    （或等价行键）；**不再按措辞漂移猜测**（拒绝机械正则），解析不到就拒收并回可用 row_id，
    已了结的行也拒收——除非显式 reopen=true（确有重开该行的理由）。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "ask_user 仅在任务期大脑回合可用"}
    q = str((args or {}).get("question") or "").strip()
    opts_in = (args or {}).get("options")
    if not q or not isinstance(opts_in, list) or not opts_in:
        return {"ok": False, "error": "invalid_args",
                "message": "参数必须是 {question, options:[{label,description?}], row?}，options 至少一项"}
    opts = []
    for o in opts_in[:4]:
        if isinstance(o, dict) and str(o.get("label") or "").strip():
            item = {"label": str(o.get("label")).strip()}
            if str(o.get("description") or "").strip():
                item["description"] = str(o.get("description")).strip()
            if o.get("recommended"):
                item["recommended"] = True
            if isinstance(o.get("pick"), dict):
                _pick = {k: v for k, v in o["pick"].items() if k in
                         ("part_id", "name", "price", "currency", "qty")}
                if _pick.get("name"):
                    item["pick"] = _pick
            if str(o.get("absent") or "").strip():
                item["absent"] = str(o["absent"]).strip()
            if o.get("waived"):
                item["waived"] = True
            # 目录字段确认选项（凡推断必求证）：声明该选项写哪个登记表字段、规范值是什么。
            # 字段 key/值域全部来自登记表契约，这里只是原样透传，不做归一。
            if str(o.get("slot") or "").strip():
                item["slot"] = str(o["slot"]).strip()
                if str(o.get("value") or "").strip():
                    item["value"] = str(o["value"]).strip()
            opts.append(item)
        elif isinstance(o, str) and o.strip():
            opts.append({"label": o.strip()})
    if not opts:
        return {"ok": False, "error": "invalid_args", "message": "options 里没有有效的 label"}
    asks = ctx.get("brain_asks")
    if not isinstance(asks, list) or asks:
        return {"ok": False, "error": "one_ask_per_turn",
                "message": "本轮已登记待答问题（one_ask_per_turn：本回合不再接受新问题）"}
    slot_arg = str((args or {}).get("slot") or "").strip()
    row_arg = str((args or {}).get("row") or "").strip()
    reopen = bool((args or {}).get("reopen"))
    # 行引用收口（2026-09-11 P2，P3-3 收紧）：行清单在场时，row 必须是清单里的 row_id 原文
    # （或等价行键）；解析不到就拒收并回可用 row_id，已了结（已锁定/豁免）的行也拒收——
    # 过去照原样接受/按措辞猜测，等于让一个手拼措辞悄悄变出一行新部件。
    # 卡片按 **row_id** 绑行：客户回答/豁免/自选料都随身份落键，引擎不必再反解文本。
    if row_arg:
        _known = [r for r in (ctx.get("kp_rows_all") or ctx.get("kp_rows_ctx") or [])
                  if isinstance(r, dict)]
        if _known:
            from app.services.part_selector import resolve_row_ref
            _hit = resolve_row_ref(row_arg, _known)
            if _hit.get("error"):
                return {"ok": False, "error": str(_hit["error"]), "row": row_arg,
                        "rows": _hit.get("candidates") or [],
                        "message": ("row 不在行清单内：只能引用清单里的既有 row_id 原文；"
                                    "新增行走 select_parts 的 new_row 声明")}
            if _hit.get("settled") and not reopen:
                return {"ok": False, "error": "row_already_settled", "row": _hit.get("row"),
                        "status": _hit.get("status"), "part": _hit.get("part"),
                        "message": ("该行已了结（" + str(_hit.get("status") or "")
                                    + ("：" + str(_hit.get("part")) if _hit.get("part") else "")
                                    + "）已了结（已锁定/已豁免）；重开该行需 reopen=true")}
            row_arg = str(_hit.get("row_id") or _hit.get("row") or row_arg)
    asks.append({"question": q, "options": opts, "row": row_arg, "slot": slot_arg})
    return {"ok": True, "message": "问题已登记，本轮结束后会向客户弹出选项卡"}
