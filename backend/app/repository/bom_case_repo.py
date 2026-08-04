# -*- coding: utf-8 -*-
"""BOM案例库仓储（rules.bom_cases）—— 时间戳业务键，无自增数字 id。

- case_key 生成：BC-YYYYMMDD-HHMMSS-ffffff（微秒精度，创建时生成，不可变）；
- kp_lines 只存 [{part_id, qty}]；详情返回时用 kp.kp_parts 解析出 name/category/最新价（展示用，不落库）；
- version 每次编辑 +1（golden 版本指纹引用）；
- 标签筛选走 JSONB ? 操作符。
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from ..models.base import Rules_SessionLocal, kp_engine, l6_engine
from ..models.bom_case import BomCase

logger = logging.getLogger(__name__)


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


def _resolve_parts(part_ids: list) -> dict:
    """part_id → {name, category, unit_price}（展示用，单一真源仍为 kp.kp_parts）。"""
    ids = [int(i) for i in (part_ids or []) if i is not None]
    if not ids:
        return {}
    out = {}
    with kp_engine.connect() as c:
        rows = c.execute(text("""
            SELECT p.id, p.name, p.oem_sku AS pn, COALESCE(c.name, '') AS category,
                   COALESCE(ph.price, 0) AS unit_price
            FROM kp.kp_parts p
            LEFT JOIN kp.kp_categories c ON p.category_id = c.id
            LEFT JOIN LATERAL (
                SELECT price FROM kp.kp_price_history
                WHERE part_id = p.id ORDER BY price_date DESC LIMIT 1
            ) ph ON true
            WHERE p.id = ANY(:ids)
        """), {"ids": ids}).mappings().all()
    for r in rows:
        out[r["id"]] = dict(r)
    return out


def _specs_str(specs) -> str:
    if not specs:
        return ""
    if isinstance(specs, str):
        return specs
    try:
        return " · ".join(f"{k}={v}" for k, v in dict(specs).items() if v not in (None, ""))
    except Exception:
        return ""


def _l6_rows_from_base_config(base_config_id) -> list:
    """基准配置 → L6 配置单行（Catalogue=件名 / Description=料号·规格 / Qty）。"""
    if not base_config_id:
        return []
    rows = []
    with l6_engine.connect() as c:
        parts = c.execute(text("""
            SELECT p.pn, p.quantity, m.name, m.category, m.specs
            FROM l6.base_config_parts p
            JOIN l6.parts_master m ON p.pn = m.pn
            WHERE p.config_id = :cid ORDER BY p.sort_order
        """), {"cid": base_config_id}).mappings().all()
    for p in parts:
        spec = _specs_str(p["specs"])
        rows.append({
            "catalogue": p["name"] or p["pn"] or "",
            "description": (p["pn"] or "") + (f" · {spec}" if spec else ""),
            "qty": p["quantity"] or 1,
        })
    return rows


def _build_bom_excel_rows(d: BomCase, kp_resolved: list) -> list:
    """案例 → BOM 行（L6 段优先用已固化的 l6_rows 快照，否则从基准配置派生 + KP 段）。"""
    rows = []
    l6 = d.l6_rows or _l6_rows_from_base_config(d.base_config_id)
    for row in l6:
        rows.append({**row, "category": "L6"})
    for ln in kp_resolved:
        if not ln.get("part_id"):
            continue  # 未关联料号行不在 BOM 里展示（编辑页补关联）
        rows.append({
            "category": "Key Parts",
            "part_category": ln.get("category") or "",
            # 型号列用件名（oem_sku 多是内部码如 S.E.E.xxx，对用户无意义）
            "catalogue": ln.get("name") or ln.get("pn") or "",
            "description": ln.get("name") or "",
            "qty": ln.get("qty") or 1,
            "base_price": ln.get("unit_price") or 0,
            "currency": "RMB",
        })
    return rows


def _classify(model_id, base_config_id=None) -> dict:
    """分类信息：系列(server_type: AI/通用…)、平台(series: Orion/Polaris)、机型(model_name)、形态(form)。"""
    out = {"server_type": "", "series": "", "model_name": "", "form": ""}
    if not model_id:
        return out
    with l6_engine.connect() as c:
        r = c.execute(text("""
            SELECT m.name AS model_name, t.name AS server_type, bc.series, bc.form
            FROM l6.server_models m
            LEFT JOIN l6.server_types t ON m.server_type_id = t.id
            LEFT JOIN l6.base_configs bc ON bc.id = m.base_config_id
            WHERE m.id = :id
        """), {"id": model_id}).mappings().first()
        if not r:
            return out
        out["model_name"] = r["model_name"] or ""
        out["server_type"] = r["server_type"] or ""
        out["series"] = r["series"] or ""
        out["form"] = r["form"] or ""
        if not out["series"] and base_config_id:
            r2 = c.execute(text("SELECT series FROM l6.base_configs WHERE id=:id"),
                           {"id": base_config_id}).mappings().first()
            out["series"] = (r2["series"] if r2 else "") or ""
    return out


def _resolve_l6_refs(model_id, base_config_id, bom_template_id) -> dict:
    """L6 机箱引用名解析（l6.server_models / base_configs / bom_templates，展示用不落库）。"""
    out = {"model_name": "", "base_config_name": "", "base_config_desc": "", "bom_template_name": ""}
    with l6_engine.connect() as c:
        if model_id:
            r = c.execute(text("SELECT name FROM l6.server_models WHERE id=:id"), {"id": model_id}).mappings().first()
            if r:
                out["model_name"] = r["name"]
        if base_config_id:
            r = c.execute(text("SELECT name, series, form, bays FROM l6.base_configs WHERE id=:id"),
                          {"id": base_config_id}).mappings().first()
            if r:
                out["base_config_name"] = r["name"]
                out["base_config_desc"] = " · ".join(x for x in (r["series"], r["form"], (f"{r['bays']}盘位" if r["bays"] else "")) if x)
        if bom_template_id:
            r = c.execute(text("SELECT name FROM l6.bom_templates WHERE id=:id"), {"id": bom_template_id}).mappings().first()
            if r:
                out["bom_template_name"] = r["name"]
    return out


def _to_dict(d: BomCase, with_parts: bool = False) -> dict:
    kp_lines = d.kp_lines or []
    resolved = {}
    if with_parts and kp_lines:
        resolved = _resolve_parts([ln.get("part_id") for ln in kp_lines])
    lines = []
    for ln in kp_lines:
        pid = ln.get("part_id")
        r = resolved.get(pid) or {}
        lines.append({
            "part_id": pid,
            "qty": ln.get("qty", 1),
            "hint": ln.get("hint") or "",
            "name": r.get("name", ""),
            "pn": r.get("pn", ""),
            "category": ln.get("category") or r.get("category", ""),
            "unit_price": r.get("unit_price", 0),
            "unresolved": not r,
        })
    l6_refs = _resolve_l6_refs(d.model_id, d.base_config_id, d.bom_template_id)
    classify = _classify(d.model_id, d.base_config_id)
    _bom_rows = _build_bom_excel_rows(d, lines) if with_parts else []
    return {
        "bom_excel_rows": _bom_rows,
        "l6_rows": d.l6_rows or [],
        "requirement": d.requirement or "",
        "l6_config_desc": d.l6_config_desc or "",
        "server_type": classify["server_type"],
        "series": classify["series"],
        "form": classify["form"],
        "model_name": classify["model_name"] or l6_refs["model_name"],
        "case_key": d.case_key,
        "name": d.name,
        "scenario_tags": d.scenario_tags or [],
        "model_id": d.model_id,
        "base_config_id": d.base_config_id,
        "bom_template_id": d.bom_template_id,
        "base_config_name": l6_refs["base_config_name"],
        "base_config_desc": l6_refs["base_config_desc"],
        "bom_template_name": l6_refs["bom_template_name"],
        "chassis_signals": d.chassis_signals or {},
        "kp_lines": lines,
        "price_snapshot": d.price_snapshot or {},
        "notes": d.notes or "",
        "version": d.version,
        "enabled": d.enabled,
        "created_at": _iso(d.created_at),
        "updated_at": _iso(d.updated_at),
        "created_by": d.created_by,
        "updated_by": d.updated_by,
    }


def _clean_kp_lines(lines: list) -> list:
    """KP 行数据卫生：已关联料号（part_id 有值）的行去掉 hint——hint 只是"未关联时用于匹配"的兜底，
    已关联行存它是冗余（2026-08-04 用户指出案例里多了型号子串）。"""
    out = []
    for l in lines or []:
        nl = dict(l or {})
        if nl.get("part_id"):
            nl.pop("hint", None)
        out.append(nl)
    return out


def new_case_key(created_at: Optional[datetime] = None) -> str:
    dt = created_at or datetime.now()
    return "BC-" + dt.strftime("%Y%m%d-%H%M%S-%f")


class BomCaseRepository:
    def __init__(self):
        self.session = Rules_SessionLocal()

    def list_cases(self, tag: Optional[str] = None, q: Optional[str] = None,
                   enabled: Optional[bool] = None, with_parts: bool = False,
                   server_type: Optional[str] = None, series: Optional[str] = None,
                   model_id: Optional[int] = None) -> list:
        query = self.session.query(BomCase)
        if enabled is not None:
            query = query.filter(BomCase.enabled == enabled)
        cases = query.order_by(BomCase.created_at.desc()).all()
        # 分类/标签/关键词过滤在内存做（数据量小）
        if model_id is not None:
            cases = [d for d in cases if d.model_id == model_id]
        if tag:
            cases = [d for d in cases if tag in (d.scenario_tags or [])]
        if q:
            ql = q.lower()
            cases = [d for d in cases if ql in (d.name or "").lower() or ql in (d.requirement or "").lower()]
        dicts = [_to_dict(d, with_parts=with_parts) for d in cases]
        if server_type:
            dicts = [d for d in dicts if d.get("server_type") == server_type]
        if series:
            dicts = [d for d in dicts if d.get("series") == series]
        return dicts

    def get_case(self, case_key: str) -> Optional[dict]:
        d = self.session.query(BomCase).filter(BomCase.case_key == case_key).first()
        return _to_dict(d, with_parts=True) if d else None

    def create_case(self, data: dict) -> dict:
        case_key = data.get("case_key") or new_case_key()
        d = BomCase(
            case_key=case_key,
            name=(data.get("name") or "").strip(),
            scenario_tags=data.get("scenario_tags") or [],
            model_id=data.get("model_id"),
            base_config_id=data.get("base_config_id"),
            bom_template_id=data.get("bom_template_id"),
            chassis_signals=data.get("chassis_signals") or {},
            kp_lines=_clean_kp_lines(data.get("kp_lines") or []),
            l6_rows=data.get("l6_rows") or _l6_rows_from_base_config(data.get("base_config_id")),
            price_snapshot=data.get("price_snapshot") or {},
            notes=data.get("notes"),
            requirement=data.get("requirement"),
            l6_config_desc=data.get("l6_config_desc"),
            version=1,
            enabled=bool(data.get("enabled", True)),
            created_by=data.get("operator") or "system",
            updated_by=data.get("operator") or "system",
        )
        if not d.name:
            raise ValueError("案例名称 name 必填")
        if not (d.requirement or "").strip():
            raise ValueError("原始需求 requirement 必填（重放/检索依赖，训练校对后案例必须携带）")
        self.session.add(d)
        self.session.commit()
        self.session.refresh(d)
        return _to_dict(d, with_parts=True)

    def _find(self, case_key: str) -> Optional[BomCase]:
        return self.session.query(BomCase).filter(BomCase.case_key == case_key).first()

    def update_case(self, case_key: str, data: dict) -> Optional[dict]:
        d = self._find(case_key)
        if not d:
            return None
        if "name" in data:
            d.name = (data["name"] or "").strip()
        if "kp_lines" in data and data["kp_lines"] is not None:
            data = {**data, "kp_lines": _clean_kp_lines(data["kp_lines"])}
        if "l6_rows" not in data and "base_config_id" in data and data["base_config_id"] is not None:
            data = {**data, "l6_rows": _l6_rows_from_base_config(data["base_config_id"])}
        for f in ("scenario_tags", "model_id", "base_config_id", "bom_template_id",
                  "chassis_signals", "kp_lines", "l6_rows", "price_snapshot", "notes", "requirement",
                  "l6_config_desc", "enabled"):
            if f in data and data[f] is not None:
                setattr(d, f, data[f])
        d.version = (d.version or 1) + 1
        d.updated_by = data.get("operator") or "system"
        self.session.commit()
        self.session.refresh(d)
        return _to_dict(d, with_parts=True)

    def delete_case(self, case_key: str) -> bool:
        d = self._find(case_key)
        if not d:
            return False
        self.session.delete(d)
        self.session.commit()
        return True

    def close(self):
        self.session.close()
