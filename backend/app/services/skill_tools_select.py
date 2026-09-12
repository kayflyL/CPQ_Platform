# -*- coding: utf-8 -*-
"""配件落地工具（select_parts）：把未匹配登记行锁定为库内真实料号。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

from app.services.skill_memory import _kp_status_rows, _slots_view
from app.services.skill_node_state import KP_CONFIG, KP_PICKS, KP_RECOMMEND, kp_state
from app.services.skill_tool_context import TOOL_CTX
from typing import Optional


def tool_select_parts(args: dict) -> dict:
    """【任务期工具】kp_reason 配件选配回合专用：把未匹配的登记部件行批量锁定为库内真实料号。

    落料（2026-09-12 直连库版）：大脑给料号名，服务端按「类目 + 名称」去库里精确核对，
    价格取库里最新值——库里没有业务料号（part_id 只是自增行号），所以名字是唯一凭据；
    库内同名多条原样回候选让 AI 确认，不猜。选定按行身份写入本节点私有状态
    kp_reason.picks 跨轮持久；客户改过该行则键失配自动作废。
    """
    ctx = TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "select_parts 仅在任务期的配件选配环节可用"}
    # 行清单为空（登记表里根本没有部件行，如「只说要一台 AI 服务器」这类极模糊需求）时
    # **不能一拒了之**：AI=配置器，它必须能自己声明要配的行（下方 row_info is None 分支写
    # kp_config）。接地照样成立——落行凭据是料号名（按类目回库精确核对，查无此名就拒）；
    # 缺类目/只有类目名的行仍会被逐行拒绝（row_unknown / category_required / spec_required）。
    rows_list = [r for r in (ctx.get("kp_rows_ctx") or []) if isinstance(r, dict)]
    from app.services.part_selector import (_ref_candidates, config_rows_to_parts,
                                            kp_registered_specified, kp_row_key,
                                            pick_entry_identity, pick_key_for_row)
    picks = (args or {}).get("picks")
    if not isinstance(picks, list) or not picks:
        return {"ok": False, "error": "invalid_args",
                "message": "参数 picks 必须是数组：[{row, part_id|name, reason}]，row 用行清单里的行键"}
    engine = ctx.get("engine")
    if not isinstance(engine, dict):
        return {"ok": False, "error": "task_not_active",
                "message": "select_parts 仅在任务期可用（缺引擎上下文）"}
    ext = ctx.get("ext") if isinstance(ctx.get("ext"), dict) else {}
    st = kp_state(engine)
    kp_picks = dict(st.get(KP_PICKS) or {})
    results = []
    declared = False

    rows_by_key = {str(r.get("row_key") or ""): r for r in rows_list}
    rows_by_id = {str(r.get("row_id") or ""): r for r in rows_list if r.get("row_id")}
    rows_by_desc = {}
    for r in rows_list:
        d = str(r.get("description") or "").strip().lower()
        if d:
            rows_by_desc.setdefault(d, r)

    def _norm(s: str) -> str:
        import re as _re
        return _re.sub(r"[\s,，、:：/]+", "", str(s or "")).lower()

    def _find_row(rid: str, rk: str, desc: str) -> Optional[dict]:
        if rid:
            hit = rows_by_id.get(rid)
            if hit:
                return hit
        if rk:
            hit = rows_by_key.get(rk) or rows_by_id.get(rk)
            if hit:
                return hit
        for probe in (desc, rk):
            if probe:
                hit = rows_by_desc.get(_norm(probe))
                if hit:
                    return hit
        # 归一化文本猜测已删除（2026-09-11 P3-3）：行身份由引擎铸造（P3-1），引用必须用
        # 清单里的 row_id 原文；解析不到就回 row_unknown，要新增同类目第二行必须显式
        # new_row=true。过去按措辞相似度"认领"一行，才是重复行/问三遍的根。
        return None

    def _upsert_pick(store: dict, rk: str, entry: dict) -> None:
        cur = store.get(rk)
        if cur is None:
            store[rk] = entry
        elif isinstance(cur, dict):
            if cur.get("part_id") == entry.get("part_id"):
                store[rk] = entry
            else:
                store[rk] = [cur, entry]
        elif isinstance(cur, list):
            for i, e in enumerate(cur):
                if isinstance(e, dict) and e.get("part_id") == entry.get("part_id"):
                    cur[i] = entry
                    return
            cur.append(entry)

    for p in picks:
        if not isinstance(p, dict):
            continue
        rid = str(p.get("row_id") or "").strip()
        rk_raw = str(p.get("row") or "").strip()
        desc_arg = str(p.get("description") or "").strip()
        pid = str(p.get("part_id") or "").strip()
        name = str(p.get("name") or "").strip()
        row_info = _find_row(rid, rk_raw, desc_arg)
        row_key = str(row_info.get("row_key") or "") if row_info else ""
        if row_info is None:
            # AI=配置器：大脑决定新增类目（如 HBA/Bridge/NVSwitch）时可声明一个尚不在清单里的行。
            # P3-3 契约（由代码强制，不是劝告句）：
            #   ① 解析不到 row_id 且没显式 new_row=true → 一律 row_unknown（不许靠措辞漂移"认领"一行，
            #      也不许悄悄铸新行——那正是同一需求长出两行、被问三遍的根）；
            #   ② new_row=true 必须写明这一行要什么（category + spec）；只有类目名/空描述 →
            #      spec_required（不铸幽灵行，回契约层让大脑问明再声明）。
            cat = str(p.get("category") or "").strip()
            spec = str(p.get("spec") or desc_arg or "").strip()
            if "|" in rk_raw:
                cat = cat or (rk_raw.split("|", 1)[0].strip())
                spec = spec or (rk_raw.split("|", 1)[1].strip())
            if not bool(p.get("new_row")):
                results.append({"row": rk_raw, "ok": False, "error": "row_unknown",
                                "rows": _ref_candidates(rows_list),
                                "message": ("row_id 不在待选行清单内。请用清单里给出的 row_id 原文；"
                                            "确要新增一行（同类目的第二种需求）必须显式 new_row=true "
                                            "并给出 category 与 spec")})
                continue
            if not cat:
                results.append({"row": rk_raw, "ok": False, "error": "category_required",
                                "message": "新增行必须给出 category（该行类目）"})
                continue
            if not spec or spec == cat:
                results.append({"row": rk_raw, "ok": False, "error": "spec_required",
                                "message": "新增行须给出 spec/description（只给类目名不接受）"})
                continue
            row_key = kp_row_key(cat, spec)
            row_info = {"row_key": row_key, "category": cat,
                        "description": spec, "qty": 1,
                        "specified": kp_registered_specified(ext, cat)}
            config = list(st.get(KP_CONFIG) or [])
            if not any((str(r.get("category") or "").strip() == cat
                        and str(r.get("spec") or r.get("description") or "").strip() == spec)
                       for r in config):
                config.append({"category": cat, "spec": spec, "qty": 1})
                st[KP_CONFIG] = config
                declared = True
            # 声明行使身份立刻与「下一次发布」同源同 id（P3-3）：用同一个铸造器
            # （config_rows_to_parts）按同一份 config 铸 origin/row_id/rev，pick 因此当场
            # 按 row_id 落键——不留 类目|描述 文本键，也不怕措辞漂移。
            for _ph in config_rows_to_parts(config):
                if (str(_ph.get("category") or "") == cat
                        and str(_ph.get("request_spec") or "") == spec):
                    row_info["origin"] = str(_ph.get("origin") or "")
                    row_info["row_id"] = str(_ph.get("row_id") or "")
                    row_info["rev"] = str(_ph.get("rev") or "")
                    break
        # P3-2：pick 的存储键 = 行身份（row_id），条目自带 category/description/rev 自证；
        # 声明出来的新行也已经铸好身份（上面），所以没有「还没身份只好退回文本键」这一档。
        store_key = pick_key_for_row(row_info)
        row_id = str(row_info.get("row_id") or "")
        cat_name = str(row_info.get("category") or "").strip()
        hit = None
        if name or pid:
            # 落料凭据 = 料号名（库里没有业务料号）；只有历史 pick 才带 part_id，走兼容通道直读
            from app.services.data_tools import lookup_part_by_id, lookup_parts_by_name
            lk: dict = {}
            matched: list = []
            if name:
                lk = lookup_parts_by_name(cat_name, name, series=str(ctx.get("kp_series") or ""),
                                          price_ok=bool(ctx.get("price_ok")))
                if lk.get("ok"):
                    matched = [h for h in (lk.get("rows") or []) if isinstance(h, dict)]
            if not matched and pid:
                lk = lookup_part_by_id(pid, price_ok=bool(ctx.get("price_ok")))
                matched = [h for h in (lk.get("rows") or []) if isinstance(h, dict)]
            if len(matched) > 1:
                results.append({"row": row_key, "ok": False, "error": "ambiguous_part",
                                "candidates": [h.get("name") for h in matched[:8]],
                                "message": (f"库内同名料号有 {len(matched)} 颗（料号库里存了重复行）："
                                            "未落料，candidates 是全部同名行")})
                continue
            if not matched:
                results.append({"row": row_key, "ok": False, "error": "no_such_part",
                                "candidates": (lk.get("out_of_scope") or None),
                                "message": str(lk.get("message") or lk.get("scope_note")
                                               or f"库里没有这个料号（类目 {cat_name}）：{name or pid}")})
                continue
            hit = matched[0]
        # 组合申报（qty）与替代申报（substitute）：白盒落 pick，落行时生效（apply_kp_picks）
        qty_raw = p.get("qty")
        qty = None
        if qty_raw is not None:
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1:
                results.append({"row": row_key, "ok": False, "error": "invalid_qty",
                                "message": "qty 必须是 ≥1 的整数（组合需求件数）"})
                continue
            if qty > 999:
                results.append({"row": row_key, "ok": False, "error": "invalid_qty",
                                "message": "qty 超出合理范围（>999），请核对组合方式"})
                continue
        substitute = bool(p.get("substitute"))
        # 抽屉字段「必填」= 该行必须落在最终方案；是否反问是运行时判定，不是字段静态开关：
        #   - 客户已明确登记具体规格（specified=True）且未标替代（substitute=False）
        #     → 库内有精确匹配，直接锁定，不反问；
        #   - 客户已明确登记具体规格但标了替代（substitute=True）→ 库内无精确料，
        #     必须反问客户（替代件/缺失处理），不许静默锁一个 AI 拍的替代料；
        #   - 客户未写明（specified=False，仅用途/类目名）→ AI 代为选料，记入推荐并
        #     反问客户选哪颗（推荐作默认项），不许静默锁一个 AI 拍的料（2026-09-09 定调）。
        customer_specified = bool(row_info.get("specified"))
        if (not customer_specified) or substitute:
            _rec = dict(st.get(KP_RECOMMEND) or {})
            _rec_entry = {**pick_entry_identity(row_info),
                          "part_id": str(hit.get("part_id") or ""),
                          "name": str(hit.get("name") or ""),
                          "price": hit.get("price"),
                          "currency": str(hit.get("currency") or "RMB"),
                          "reason": str(p.get("reason") or "").strip()}
            if qty is not None:
                _rec_entry["qty"] = qty
            _upsert_pick(_rec, store_key, _rec_entry)
            st[KP_RECOMMEND] = _rec
            results.append({"row": row_key, "row_id": rid or row_key, "ok": True, "recommended": {
                "part_id": str(hit.get("part_id") or ""), "name": str(hit.get("name") or "")}})
            continue
        pick_entry = {
            **pick_entry_identity(row_info),
            "part_id": str(hit.get("part_id") or ""),
            "name": str(hit.get("name") or ""),
            "price": hit.get("price"),
            "currency": str(hit.get("currency") or "RMB"),
            "reason": str(p.get("reason") or "").strip(),
        }
        if qty is not None:
            pick_entry["qty"] = qty
        if substitute:
            pick_entry["substitute"] = True
        _upsert_pick(kp_picks, store_key, pick_entry)
        results.append({"row": row_key, "row_id": row_id or rid or row_key, "ok": True,
                        "selected": {"part_id": str(hit.get("part_id") or ""),
                                     "name": str(hit.get("name") or "")}})
    ok_rows = [r for r in results if r.get("ok")]
    if ok_rows or declared:
        st[KP_PICKS] = kp_picks
        save = ctx.get("save")
        if callable(save):
            save()
    recs = [r for r in results if r.get("recommended")]
    locked = [r for r in results if r.get("selected")]
    if recs and locked:
        msg = (f"已锁定 {len(locked)}/{len(results)} 行真实料号；另有 {len(recs)} 行为 AI 推荐"
               "（待客户确认，未落地为锁定）")
    elif recs:
        msg = f"已登记 {len(recs)} 行 AI 推荐（待客户确认，未落地为锁定）"
    else:
        msg = f"已锁定 {len(ok_rows)}/{len(results)} 行真实料号"
    return {"ok": bool(ok_rows) and len(ok_rows) == len(results),
            "results": results,
            "message": msg,
            "current": _slots_view(ext),
            "rows": _kp_status_rows()}
