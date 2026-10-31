# -*- coding: utf-8 -*-
"""CPQ 域产物实现（宿主侧，2026-10-31 路线图 v4 第 1 步「装注册插座」）。

引擎（skill_node_artifacts）只留注册表机制；本文件是 CPQ 的插头实现——登记表/KP 表/
方案卡等 7 个产物生成器 + 线索登记表实时发射器，import 时自注册进引擎插座
（同 register_formatter「宿主被 import 时自注册」先例；引擎侧 ensure_registered 惰性触发）。

新域接产物 = 另写一个宿主实现文件注册自己的 builder，引擎零改动（v4 主线第 4 步
AI 接入向导替新办公室起草的就是这类声明）。
"""
from __future__ import annotations

import logging

from app.services.skill_node_artifacts import (
    register_builder,
    register_live_emitter,
)
from app.services.skill_target_contract import (
    first_artifact,
    shape_table_rows,
    unresolved_columns,
)

logger = logging.getLogger(__name__)

KP_TABLE_FALLBACK_COLUMNS = [
    {"key": "part_category", "label": "Catalogue"},
    {"key": "catalogue", "label": "Configuration Description"},
    {"key": "qty", "label": "Quantity", "width": 90},
]

# 组装节点（方案配置表）兜底列：行键与真实方案配置表同源（见 portal_flow_adapter._normalize_sheet_row）；
# L6 行没有 part_category，故回退到行上的 category（'L6' / 'Key Parts'），不静默空列
COMPOSE_FALLBACK_COLUMNS = [
    {"key": "part_category", "label": "Catalogue", "from": "part_category", "fallback": "category"},
    {"key": "catalogue", "label": "Configuration Description", "from": "catalogue", "fallback": "name"},
    {"key": "qty", "label": "Quantity", "from": "qty", "fallback": "1", "width": 90},
]


def _visible_columns(art: dict, fallback: list) -> list:
    """展示列 = 插头 columns（visible 过滤）的 key/label；插头没配才用兜底三列。

    展示列只描述「表格长什么样」；取值链（from/fallback）见 _shape_columns——两者分开，
    免得渲染用的列名被当成取值契约去校验。
    """
    return [{"key": str(c.get("key")).strip(), "label": str(c.get("label") or c.get("key"))}
            for c in _shape_columns(art, [])] or list(fallback)


def _shape_columns(art: dict, fallback: list) -> list:
    """整形列契约 = 插头 columns 原样（含 from/fallback 取值链，visible 过滤）。"""
    cols = [c for c in (art.get("columns") or [])
            if isinstance(c, dict) and c.get("visible", True) is not False
            and str(c.get("key") or "").strip()]
    return cols or list(fallback)


def locked_l6_rows(locked: dict) -> list:
    """锁定机型 → L6 机箱表行（BOM 模板求值；模板/求值失败回退基准配置行）。

    与目标层抽屉预览（/l6-preview）、方案配置页 L6 段同源同形状：机型阶段无配件无信号，
    传空 kp_lines/chassis_signals = 基础机箱（配件与选型规则影响由组装节点结算）。
    """
    base_id = (locked or {}).get("id")
    if not base_id:
        return []
    rows: list = []
    template_id = (locked or {}).get("bom_template_id")
    try:
        if template_id:
            from app.services.bom_template_eval import eval_l6_rows
            rows = eval_l6_rows(int(template_id), int(base_id), [], {}) or []
    except Exception:
        logger.exception("model_reason L6 模板求值失败 template=%s base=%s", template_id, base_id)
        rows = []
    if not rows:
        try:
            from app.repository.bom_case_repo import _l6_rows_from_base_config
            rows = _l6_rows_from_base_config(base_id)
        except Exception:
            logger.exception("model_reason L6 基准配置行回退失败 base=%s", base_id)
            rows = []
    return rows


def _l6_chassis(engine: dict, art: dict) -> tuple:
    locked = engine.get("_locked_baseline") or {}
    name = locked.get("name") or str((engine.get("ext") or {}).get("server_model") or "").strip()
    reason = engine.get("lock_reason") or ""
    pool = [c.get("name") or "" for c in (engine.get("baselines_pool") or []) if isinstance(c, dict)]
    rows = locked_l6_rows(locked)
    output = {"chosen": name, "reason": reason, "matches": [{"name": name}] if name else [],
              "pool_count": len(pool), "l6_rows_count": len(rows)}
    artifact = {"kind": "l6_chassis", "title": str(art.get("name") or "机箱表（L6 配置）"),
                "data": {"chosen": name, "reason": reason, "rows": rows,
                         "columns": _visible_columns(art, [
                             {"key": "catalogue", "label": "配置件"},
                             {"key": "description", "label": "说明"},
                             {"key": "qty", "label": "数量"}])}}
    return output, artifact


def _kp_table_row(p: dict) -> dict:
    cat = str(p.get("category") or p.get("part_category") or "").strip()
    name = str(p.get("name") or p.get("pn") or "").strip()
    spec = str(p.get("request_spec") or "").strip() or str(p.get("grounded_spec") or "").strip()
    qty = p.get("qty")
    try:
        qty = int(qty) if qty is not None else 1
    except (TypeError, ValueError):
        qty = 1
    waived = bool(p.get("waived"))
    return {"part_category": cat,
            "catalogue": name or spec or cat,
            "qty": qty,
            "description": spec,
            "unmatched": bool(p.get("unmatched")),
            # 白盒第三结局：库内无料、客户已知悉并保持原需求（行保留 + 标注，终检放行）
            "waived": waived,
            "waived_note": "库内无料，客户已知悉（保持原需求）" if waived else ""}


def _kp_table(engine: dict, art: dict) -> tuple:
    summary_map = dict(engine.get("kp_summary") or {})
    parts = [p for p in (engine.get("kp_parts") or []) if isinstance(p, dict)]
    output = dict(summary_map)
    rows = [_kp_table_row(p) for p in parts]
    columns = _visible_columns(art, KP_TABLE_FALLBACK_COLUMNS)
    if rows:
        # 边沿一致性（不静默空列）：抽屉列契约 vs 真实产物行，取不出值即告警。
        bad = unresolved_columns({"columns": columns}, rows[0])
        if bad:
            logger.warning("kp_table 列契约与产物行对不上（这些列会是空的）：%s", bad)
    artifact = {"kind": "kp_table", "title": str(art.get("name") or "配件选型"),
                "data": {"summary": summary_map, "rows": rows,
                         "columns": columns,
                         "unmatched": [p for p in parts if p.get("unmatched")]}}
    return output, artifact


def _plans(engine: dict, art: dict) -> tuple:
    """组装节点产物 = 完整方案配置表（L6 + KP 的组装结果行）+ 整机方案清单。

    行取自引擎事实（plans[].cfg.bom_excel_rows，即 BOM 模板求值后的真实行），
    列契约读抽屉（改抽屉列定义 → 这里跟着变），形状与商机详情页方案配置表一致。
    """
    plans = [p for p in (engine.get("plans") or []) if isinstance(p, dict)]
    rows = []
    for p in plans:
        cfg = p.get("cfg") if isinstance(p.get("cfg"), dict) else {}
        rows += [r for r in (cfg.get("bom_excel_rows") or []) if isinstance(r, dict)]
    shape_cols = _shape_columns(art, COMPOSE_FALLBACK_COLUMNS)
    shaped = shape_table_rows({"columns": shape_cols}, rows, extra_keys=("category",))
    columns = _visible_columns(art, COMPOSE_FALLBACK_COLUMNS)
    if rows:
        bad = unresolved_columns({"columns": shape_cols}, rows[0])
        if bad:
            logger.warning("plans 列契约与组装行对不上（这些列会是空的）：%s", bad)
    output = {"plans_count": len(plans),
              "plan_names": [p.get("model") or p.get("name") or "" for p in plans]}
    artifact = {"kind": "plans", "title": str(art.get("name") or "BOM 组装结果"),
                "data": {"plans_count": len(plans), "plans": plans,
                         "rows": shaped, "columns": columns}}
    return output, artifact


def _bom_scheme(engine: dict, art: dict) -> tuple:
    payload = dict(engine.get("output_payload") or {})
    plans = engine.get("plans") or []
    output = payload or {"plans_count": len(plans)}
    artifact = {"kind": "bom_scheme", "title": str(art.get("name") or "方案配置卡"),
                "data": payload}
    return output, artifact


def _requirement_text(engine: dict, art: dict) -> tuple:
    text = str(engine.get("requirement_text") or "")
    output = {"requirement_text": text, "opportunity_id": str(engine.get("opportunity_id") or "")}
    return output, {"kind": "requirement_text", "title": str(art.get("name") or "需求原文"),
                    "data": {"text": text, "opportunity_id": str(engine.get("opportunity_id") or "")}}


def _requirement_slots(engine: dict, art: dict) -> tuple:
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    slots = requirement_slots_from_ext(dict(engine.get("ext") or {}))
    output = {"missing_critical": list(engine.get("blockers") or [])}
    return output, {"kind": "requirement_slots", "title": str(art.get("name") or "线索登记表"),
                    "data": dict(slots)}


def _data_report(engine: dict, art: dict) -> tuple:
    answer = str(((engine.get("agent_result") or {}).get("answer")) or "")
    output = {"answer_chars": len(answer)} if answer else {}
    return output, {"kind": "document", "title": str(art.get("name") or "数据报告"),
                    "data": {"markdown": answer}}


async def _live_requirement_slots(engine: dict, event_sink, label: str,
                                  started: float, text: str = "") -> None:
    """线索登记表的实时发射器：先按必填闸门口径刷新缺口，再逐项亮已登记内容。"""
    from app.services.skill_plan_runtime import _emit_requirement_fill
    from app.services.slot_contract import _missing_critical
    from app.services.capabilities import _slot_now_filled
    ext_now = engine.get("ext") or {}
    engine["blockers"] = [m for m in _missing_critical(ext_now)
                          if not _slot_now_filled(ext_now, m)]
    await _emit_requirement_fill(engine, event_sink, label, started, text)


# ── 自注册：import 本模块即把 CPQ 插头插进引擎插座 ────────────────────────────

register_builder("requirement_text", _requirement_text)
register_builder("l6_chassis", _l6_chassis)
register_builder("kp_table", _kp_table)
register_builder("plans", _plans)
register_builder("bom_scheme", _bom_scheme)
register_builder("requirement_slots", _requirement_slots)
register_builder("data_report", _data_report)
register_live_emitter("requirement_slots", _live_requirement_slots)
