# -*- coding: utf-8 -*-
"""part_selector —— 干净版配件选型（供 agent 工具使用）。

与旧 pick_kp_parts 的区别：不做 600 行正则/每部件特判；只做四件事——
  1) 品类解析（读规则库 type_package/conditional_kp_categories）
  2) 需求品类→库品类映射（读规则库 category_alias + token 兜底）
  3) 查库取最新价（按价格升序）
  4) 选代表件（min_price/max_price/first）
一切业务词/品类来自 requirement_rule_catalog；AI 只需给"要什么"，工具决定"怎么挑"。
"""
from __future__ import annotations

import re
from typing import Optional

from app.repository.kp_repo import KPRepository


def _resolve_categories(categories: Optional[list], server_type_name: Optional[str]) -> list[str]:
    """按显式 categories，或用 server_type 的规则套餐（type_package + 条件品类）推断。"""
    if categories:
        return [str(c) for c in categories if c]
    if not server_type_name:
        return []
    from app.services.requirement_rule_catalog import type_packages, conditional_kp_categories
    pkgs = type_packages()
    cats: list[str] = []
    flags: dict = {}
    for pkg in pkgs:
        kw = str(pkg.get("type_keyword") or "")
        if kw and kw in server_type_name:
            cats = list(pkg.get("categories") or [])
            flags = {str(k): bool(v) for k, v in pkg.items() if str(k).startswith("mandatory_")}
            break
    cond = conditional_kp_categories() or {}
    for cat, spec in cond.items():
        if cat not in cats:
            continue
        flag = str(spec.get("package_flag") or "")
        if flag and flags.get(flag):
            continue
        cats = [c for c in cats if c != cat]
    return cats


def _match_category(need_cat: str, db_cats: list[str], aliases_map: Optional[dict]) -> Optional[str]:
    """需求品类 → 命中的 KP 库分类名（先别名精确，再子串，再 token 兜底）。无命中 None。"""
    aliases = (aliases_map or {}).get(need_cat, [])
    db_low = {c: (c or "").lower() for c in db_cats}
    for a in aliases:
        a = str(a).lower()
        for c, cl in db_low.items():
            if cl == a:
                return c
    for a in aliases:
        a = str(a).lower()
        for c, cl in db_low.items():
            if a in cl or cl in a:
                return c
    for tok in re.split(r"[/\s]+", (need_cat or "").lower()):
        if len(tok) < 2:
            continue
        for c, cl in db_low.items():
            if tok in cl:
                return c
    return None


def _pick_rep(rows: list[dict], mode: str) -> Optional[dict]:
    if not rows:
        return None
    if mode == "max_price":
        return max(rows, key=lambda r: float(r.get("price") or 0))
    if mode == "first":
        return rows[0]
    return min(rows, key=lambda r: float(r.get("price") or 0))


def select_parts(categories: Optional[list] = None,
                 server_type_name: Optional[str] = None,
                 search: Optional[str] = None,
                 qty_map: Optional[dict] = None,
                 representative_pick: str = "min_price") -> list[dict]:
    """按品类查 KP 库选代表件，返回 build_plan 可消费的部件列表。"""
    cats = _resolve_categories(categories, server_type_name)
    if not cats:
        return []
    from app.services.requirement_rule_catalog import category_aliases
    aliases = category_aliases()
    repo = KPRepository()
    try:
        db_cats = [str(c.get("category") or c.get("name") or "")
                   for c in repo.get_categories()
                   if (c.get("category") or c.get("name"))]
        qty = qty_map or {}
        parts: list[dict] = []
        for cat in cats:
            db_cat = _match_category(cat, db_cats, aliases)
            kw = (search or "").strip()
            if not db_cat:
                parts.append({"category": cat, "pn": "", "name": "", "unit_price": 0.0,
                              "currency": "RMB", "qty": int(qty.get(cat) or qty.get("") or 1),
                              "matched_spec": "", "unmatched": True,
                              "unmatched_reason": f"库无 {cat} 分类"})
                continue
            rows = repo.get_latest_prices(search=kw, category=db_cat,
                                          sort_by="price", sort_order="asc",
                                          include_record_count=False)
            q = int(qty.get(cat) or qty.get(db_cat) or 1)
            rep = _pick_rep(rows, representative_pick)
            if rep:
                parts.append({
                    "category": cat,
                    "pn": str(rep.get("model") or ""),
                    "name": str(rep.get("model") or ""),
                    "unit_price": float(rep.get("price") or 0),
                    "currency": str(rep.get("currency") or "RMB"),
                    "qty": q,
                    "matched_spec": "",
                    "unmatched": False,
                })
            else:
                parts.append({"category": cat, "pn": "", "name": "", "unit_price": 0.0,
                              "currency": "RMB", "qty": q, "matched_spec": "", "unmatched": True,
                              "unmatched_reason": f"库无 {cat} 替代件/价"})
        return parts
    finally:
        repo.close()
