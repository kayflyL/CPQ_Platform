# -*- coding: utf-8 -*-
"""节点产物打包（插头解释器·产物侧）。

插座 = 节点机制（本模块 + 消费方）；插头 = 节点配置 target.artifacts[]（DB 唯一权威）。
机制只认产物槽注册表（BUILDERS），不认具体节点：换/加目标表 = 注册一个 builder 并在抽屉
声明 slot，节点循环与主循环零改动（铁律⑤「换目标层不碰代码生效」的验收口径）。

插头两栏针脚（各司其职，不互相顶替）：
  slot  装什么 = 产物槽（BUILDERS 的键，本模块分发认它，**只由抽屉声明**，代码无节点→产物表）
  kind  怎么显示 = 渲染类型（form/table/document/...，前端抽屉预览认它，不参与分发）

产物来源是引擎事实（engine 里的产物槽），不是另建一份表：
  l6_chassis        <- engine._locked_baseline（机型阶段产物）+ BOM 模板求值
  kp_table          <- engine.kp_parts（kp_reason 产物）
  plans             <- engine.plans（compose 产物）
  bom_scheme        <- engine.output_payload（output 产物）
  requirement_slots <- engine.ext（线索登记表，agent_fill 产物）

未注册 kind 的节点：产物为空（不装懂），只在 output 里给白盒事实。
"""
from __future__ import annotations

import logging

from app.services.skill_target_contract import first_artifact

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


async def emit_live_artifact(node_key: str, engine: dict, event_sink, label: str,
                             started: float, text: str = "") -> bool:
    """节点回合内的实时产物广播（边干边亮）：该节点声明的产物槽注册了实时发射器才发。

    「这一步边想边亮」是产物槽的属性（见 LIVE_EMITTERS），不是节点名的属性：主循环只问
    有没有实时产物，不认节点名。换插头（把 slot 换成别的产物槽）→ 实时行为跟着换。
    """
    emitter = LIVE_EMITTERS.get(resolve_kind(engine, node_key))
    if emitter is None:
        return False
    await emitter(engine, event_sink, label, started, text)
    return True


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


# 注册「产物槽 → 回合内实时发射器」：实时可视化是产物槽的属性，不是节点名的属性
LIVE_EMITTERS = {"requirement_slots": _live_requirement_slots}


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
        from app.services.skill_target_contract import unresolved_columns
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
    from app.services.skill_target_contract import shape_table_rows, unresolved_columns
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


# kind 注册表：新增插头类型 = 注册一个 builder，机制零改动
BUILDERS = {
    "requirement_text": _requirement_text,
    "l6_chassis": _l6_chassis,
    "kp_table": _kp_table,
    "plans": _plans,
    "bom_scheme": _bom_scheme,
    "requirement_slots": _requirement_slots,
}


def declared_slot(engine: dict, key: str) -> str:
    """抽屉插头声明的产物槽：target.artifacts[0].slot（权威针脚）。

    过渡期兼容 output_artifact：仅当它的值恰好是已注册产物槽时才认（老库把产物槽写在
    这个字段里，如 requirement_text / plans）；值不是产物槽（如 'ext / requirement'）
    视为未声明，不猜。
    """
    node_cfg = ((engine.get("flow_configs") or {}).get(key)
                if isinstance(engine.get("flow_configs"), dict) else None)
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    slot = str((first_artifact(cfg) or {}).get("slot") or "").strip()
    if not slot:
        leg = str(cfg.get("output_artifact") or "").strip()
        if leg in BUILDERS:
            slot = leg
    return slot


def resolve_kind(engine: dict, key: str) -> str:
    """产物槽分发：**完全由抽屉声明**（换插头生效），代码里没有「节点 → 产物」硬编码表。

    针脚分两栏：`slot` = 装什么（产物注册表键，本函数认它）；`kind` = 怎么显示
    （form/table/... 渲染类型，前端认它，不参与分发）。没声明 slot 的节点产物为空
    ——白盒不装懂，绝不按节点名兜底（否则换插头换不掉）。
    """
    slot = declared_slot(engine, key)
    return slot if slot in BUILDERS else ""


def done_summary(engine: dict, key: str, artifact: dict, vres: dict = None) -> str:
    """节点完成摘要：从该节点**真实产物**生成——产物是空的就如实说空，不报「已完成」。

    摘要不许再按节点 key 硬编码文案（历史事故：agent_fill 完成时显示「配件选型完成」）。
    """
    art = artifact if isinstance(artifact, dict) else {}
    data = art.get("data") if isinstance(art.get("data"), dict) else {}
    title = str(art.get("title") or "").strip() or str(key)
    if not art:
        return title + "：本节点未注册产物"
    vres = vres if isinstance(vres, dict) else {}
    kind = str(art.get("kind") or "")
    bits: list = []
    if str(vres.get("locked") or "").strip():
        bits.append("机型「" + str(vres["locked"]) + "」")
    rows = data.get("rows")
    if isinstance(rows, list) and rows:
        bits.append(str(len(rows)) + " 行")
        waived = [r for r in rows if isinstance(r, dict) and r.get("waived")]
        if waived:
            bits.append(f"其中 {len(waived)} 行库内无料·客户已知悉")
    plans = data.get("plans")
    n_plans = len(plans) if isinstance(plans, list) else data.get("plans_count")
    if isinstance(n_plans, int) and n_plans > 0:
        bits.append(str(n_plans) + " 个整机配置")
    if kind == "requirement_slots" and not bits:
        filled = len([k for k, v in data.items() if v not in (None, "", [], {})])
        if filled:
            bits.append(str(filled) + " 项已登记")
    if bits:
        return title + " · " + " / ".join(bits)
    return (title + " 已生成") if data else (title + "（产物为空）")


def node_payload(engine: dict, key: str, label: str, summary: str, vres: dict = None) -> dict:
    """节点完成广播载荷：summary + 该节点真实产物（output/artifact）。

    供画布节点卡在节点下方展示「产出 / 输出物」；kind 未知则产物为空（白盒不装懂）。
    summary 留空时由产物生成（见 done_summary）。
    """
    output = None
    artifact = None
    try:
        node_cfg = ((engine.get("flow_configs") or {}).get(key)
                    if isinstance(engine.get("flow_configs"), dict) else None)
        art = first_artifact(node_cfg) or {}
        builder = BUILDERS.get(resolve_kind(engine, key))
        if builder is not None:
            output, artifact = builder(engine, art)
    except Exception:
        logger.exception("节点产物打包失败 step=%s", key)
        output, artifact = None, None
    if not summary:
        summary = done_summary(engine, key, artifact, vres)
    return {"type": "node_trace", "step": key, "label": label, "status": "done",
            "input": None, "output": output, "summary": summary or "", "artifact": artifact}
