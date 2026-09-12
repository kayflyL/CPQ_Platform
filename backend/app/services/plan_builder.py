# -*- coding: utf-8 -*-
"""整机方案组装能力：单机型基准（baseline）+ KP 配件清单 → 完整整机方案（plan + BOM 快照）。

能力归属（树干-枝叶）：compose/BOM 组装节点的执行核心。内部惰性接入两类枝叶——
策略规则（plan_rule_apply.apply_plan_selection_rules，规则存策略中心）与
BOM 模板（bom_template_eval.eval_l6_rows，模板存 DB）；背板对齐/电源档位钳制/
货币折算为组装机制。消费方：skill_node_runtime.compose_plans（BOM 组装节点引擎）。
2026-09-02 自 app/api/candidate_search.py 原样迁入（纯搬移零行为变化）。
"""
import logging
import re
from typing import Optional

from app.repository.base_config_repo import BaseConfigRepository
from app.repository.parts_master_repo import PartsMasterRepository

logger = logging.getLogger(__name__)


def _specs_str(specs) -> str:
    """specs dict → 短摘要串（取前 2 个 key=value），渲染用。"""
    if not specs or not isinstance(specs, dict):
        return ""
    try:
        items = [f"{k}={v}" for k, v in list(specs.items())[:2] if v not in (None, "")]
        return " · ".join(items)
    except Exception:
        return ""


def _find_backplane_part(bt: str) -> Optional[dict]:
    """料号库找目标背板件（category=前置硬盘背板 + specs.bt == bt），找不到返回 None。"""
    try:
        repo = PartsMasterRepository()
        parts = repo.list(category="前置硬盘背板")
    except Exception as e:
        logger.warning("读取背板料号失败 bt=%s: %s", bt, e)
        return None
    for p in parts or []:
        if (p.get("specs") or {}).get("bt") == bt:
            return p
    return None


def _sync_plan_backplane(plan: dict, base_parts: list) -> None:
    """方案 BOM 背板件与派生 bp_type 对齐（2026-08-03 第一轮训练发现）：
    bp_type=tri 但基线 BOM 行是直连背板（如 ES22V3-P 基线为 Orion 2U12 直连版）时，
    把 bom_excel_rows 背板行换成料号库同 bt 的件并补价差（l6_cost/total_cost）。
    无目标件/解析失败 → 保留原行不阻塞（方案照常出）。"""
    bp_type = (plan.get("chassis_signals") or {}).get("bp_type")
    if bp_type not in ("tri", "dc"):
        return
    rows = (plan.get("cfg") or {}).get("bom_excel_rows") or []
    if not rows:
        return

    def _bt_of(blob: str) -> Optional[str]:
        if re.search(r"\bbt\s*=\s*tri|tri-?mode", blob, re.I):
            return "tri"
        if re.search(r"\bbt\s*=\s*dc|pass-?thru|直连", blob, re.I):
            return "dc"
        return None

    bp_rows = [r for r in rows if re.search(r"背板|backplane|pass-?thru|tri-?mode", f"{r.get('catalogue') or ''} {r.get('description') or ''}", re.I)]
    changed = False
    for r in bp_rows:
        blob = f"{r.get('catalogue') or ''} {r.get('description') or ''}"
        if _bt_of(blob) != bp_type:
            changed = True
            break
    if not changed:
        return  # 已对齐（或无 bt 标注——不动，避免误判）

    new_part = _find_backplane_part(bp_type)
    if not new_part:
        return
    old_price = None
    for p in base_parts or []:
        if re.search(r"背板|backplane", p.get("category") or "", re.I):
            try:
                old_price = float(p.get("unit_price") or 0)
            except (TypeError, ValueError):
                old_price = None
            break
    _bt = (new_part.get("specs") or {}).get("bt") or bp_type
    for r in bp_rows:
        blob = f"{r.get('catalogue') or ''} {r.get('description') or ''}"
        if _bt_of(blob) == bp_type:
            continue
        r["catalogue"] = new_part.get("name") or new_part.get("pn") or r.get("catalogue")
        r["description"] = (new_part.get("pn") or "") + f" · bt={_bt}"
    if old_price is not None:
        try:
            delta = float(new_part.get("unit_price") or 0) - old_price
        except (TypeError, ValueError):
            delta = 0.0
        summary = plan.setdefault("summary", {})
        summary["l6_cost"] = round(float(summary.get("l6_cost") or 0) + delta, 2)
        summary["total_cost"] = round(float(summary.get("total_cost") or 0) + delta, 2)


def _clamp_psu_wattage(w: str, allowed_wattages=None) -> str:
    """把推断瓦数收敛到机型允许档位（基准配置 psu_wattages，如 ES22V3-P=[1300,1600,2000]）。
    未配置/非法档位列表 → 原样返回（沿用全局档位）；推断值不在档内 →
    取 ≥推断值的最小档，无更高档则取最大档（机型物理上限，宁高勿低）。"""
    try:
        w_int = int(float(w))
    except (TypeError, ValueError):
        return w
    if not allowed_wattages:
        return w
    try:
        allowed = sorted({int(float(x)) for x in allowed_wattages if x not in (None, "")})
    except (TypeError, ValueError):
        return w
    if not allowed:
        return w
    if w_int in allowed:
        return str(w_int)
    for a in allowed:
        if a >= w_int:
            return str(a)
    return str(allowed[-1])


def build_plan(baseline: dict, kp_parts: list[dict], psu_wattage: Optional[str] = None,
               psu_qty: Optional[int] = None) -> dict:
    """单 baseline + KP 列表 → 整机方案（含喂给 BomTable 的 excel 快照 cfg）。
    matched 件正常进入 kp_rows；unmatched 件也保留为「待手填」占位行进入 bom_excel_rows，
    同时额外写入 plan.unmatched，前端方案卡继续用 unmatched 标"需手填"badge。
    这样不会因为所有关键件都还没落 SKU，就让最终 BOM 的 kp_rows 变成空表。"""
    bc_repo = BaseConfigRepository()
    full = bc_repo.get_with_parts(baseline.get("id")) or {}
    parts = full.get("parts") or []

    matched_kp = [kp for kp in kp_parts if not kp.get("unmatched")]
    unmatched_kp = [kp for kp in kp_parts if kp.get("unmatched")]
    unmatched_items = [{
        "category": kp.get("category") or "",
        "reason": kp.get("unmatched_reason") or "规格未命中，需手填",
    } for kp in kp_parts if kp.get("unmatched")]

    # 电源瓦数：不做引擎推断——只取 AI 语义层/人工传入值（psu_wattage），
    # 再按机型物理支持档位（baseline.psu_wattages，业务事实）收敛；未给值 → 留空（模板手填）。
    chassis_signals = {}
    if psu_wattage not in (None, ""):
        chassis_signals["psu_wattage"] = _clamp_psu_wattage(str(psu_wattage), baseline.get("psu_wattages"))
    if psu_qty is not None:
        chassis_signals["psu_qty"] = int(psu_qty)

    # 先执行选型配置规则，补出 bp_type / cable_qty_by_kind，再求值 L6 模板。
    # 这里不能沿用内部料号平铺；必须与人工方案配置共用同一套 BOM 模板。
    selection_alerts: list = []
    try:
        from app.services.plan_rule_apply import apply_plan_selection_rules
        signal_plan = {"chassis_signals": chassis_signals}
        apply_plan_selection_rules(signal_plan, matched_kp, baseline)
        chassis_signals = signal_plan.get("chassis_signals") or chassis_signals
        selection_alerts = signal_plan.get("selection_alerts") or []
    except Exception:
        logger.exception("apply_plan_selection_rules failed; plan continues without rule-derived signals")

    template_id = baseline.get("bom_template_id")
    used_template_l6 = False
    if template_id and baseline.get("id"):
        try:
            from app.services.bom_template_eval import eval_l6_rows
            raw_l6 = eval_l6_rows(
                int(template_id), int(baseline.get("id")), matched_kp, chassis_signals
            )
            l6_rows = [{"category": "L6", **dict(row)} for row in raw_l6]
            used_template_l6 = True
        except Exception:
            logger.exception("eval_l6_rows failed; fallback to base-config L6 rows template_id=%s", template_id)
            used_template_l6 = False

    if not used_template_l6:
        l6_rows = [{
            "category": "L6",
            "catalogue": p.get("name") or p.get("pn") or "",
            "description": (p.get("pn") or "") + (f" · {_specs_str(p.get('specs'))}" if _specs_str(p.get('specs')) else ""),
            "qty": p.get("quantity") or 1,
        } for p in parts]

    def _kp_sheet_row(kp: dict) -> dict:
        return {
            "category": "Key Parts",
            "catalogue": kp.get("pn") or "",
            "description": (kp.get("name") or "") + (f" · {kp['matched_spec']}" if kp.get("matched_spec") else "")
                          + (f" · {kp['replacement_note']}" if kp.get("replacement_note") else ""),
            "part_category": kp.get("category") or "",
            "qty": kp.get("qty") or 1,
            "base_price": kp.get("unit_price") or 0,
            "currency": kp.get("currency") or "RMB",
            "note": kp.get("note") or "",
        }

    # 方案配置表 KP 部分 = 库内真实料号（2026-09-06 用户定调）：未匹配占位行不落表——
    # 客户原话/空描述混进配件表=黑盒污染；缺配信息由硬门征询卡与汇报旁白承载
    kp_rows = [_kp_sheet_row(kp) for kp in matched_kp]

    # 货币折算（口径对齐报价工作台 store/quote.ts:194）：USD 件 base 不含税 → ×汇率×(1+增值税率) 折成含税 RMB；
    # RMB 件已含税直用；baseline（底盘）currency=RMB 已含税。total_cost 统一为含税 RMB，避免美元数值当人民币混加。
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        _cfg = SystemConfigRepository()
        try:
            tax_rate = float(_cfg.get_value("tax_rate", 0.13))
            usd_to_rmb = float(_cfg.get_value("usd_to_rmb", 7.0))
        finally:
            _cfg.close()
    except Exception:
        tax_rate, usd_to_rmb = 0.13, 7.0

    def _rmb(price, currency):
        p = float(price or 0)
        return p * usd_to_rmb * (1 + tax_rate) if str(currency or "RMB").upper() == "USD" else p

    l6_cost = float(baseline.get("total_price") or 0)
    kp_cost = sum(_rmb(kp.get("unit_price"), kp.get("currency")) * (kp.get("qty") or 1) for kp in matched_kp)
    total_cost = l6_cost + kp_cost

    plan = {
        "config_id": baseline.get("id"),
        "server_model_id": baseline.get("server_model_id"),
        "name": baseline.get("name") or "",
        "use": baseline.get("use") or "",
        "product_content": baseline.get("product_content"),
        "model": baseline.get("model") or "",
        "series": baseline.get("series") or "",
        "form": baseline.get("form") or "",
        "bays": baseline.get("bays"),
        "bom_template_id": baseline.get("bom_template_id"),
        "chassis_signals": chassis_signals,
        "recommend_level": baseline.get("recommend_level") or "",
        "selling_points": baseline.get("selling_points") or "",
        "selection_alerts": selection_alerts,
        "unmatched": unmatched_items,
        "summary": {
            "parts_count": int(baseline.get("parts_count") or 0),
            "kp_count": len(kp_rows),
            "unmatched_count": len(unmatched_items),
            "l6_cost": round(l6_cost, 2),
            "kp_cost": round(kp_cost, 2),
            "total_cost": round(total_cost, 2),
            "currency": "RMB",  # total_cost 已折算统一为含税 RMB（USD 件 ×usd_to_rmb×(1+tax_rate)）
            "rates": {"usd_to_rmb": usd_to_rmb, "tax_rate": tax_rate},
        },
        "cfg": {
            "bom_source": "excel",
            "bom_excel_rows": l6_rows + kp_rows,
        },
    }

    # 背板件与派生 bp_type 对齐只用于旧的内部料号平铺降级路径；BOM 模板求值已按 bp_type 渲染。
    if not used_template_l6:
        try:
            _sync_plan_backplane(plan, parts)
        except Exception:
            logger.exception("sync plan backplane failed; plan keeps original rows")

    return plan
