# -*- coding: utf-8 -*-
"""推理节点默认契约的 DB 引导（一次性空库播种；DB 运行后唯一权威）。

职责：在 rules.reasoning_node_default 为空时，把「需求分析节点默认契约」的**结构**写入新表：
节点用哪些工具、产物装进哪个槽、哪些开关是确定的。**不含任何提示词文案**——节点使命
说明（description/goal/system_prompt）与任务规则（manual_rules）的唯一出处是 Skill Studio
左栏（DB 行，用户可编辑）；代码里不留第二套。

只补缺失行，不覆盖已有行；运行后业务代码一律只读这张表，绝不回退到本模块常量。
"""
from __future__ import annotations
import json
from datetime import datetime

from app.models.base import Rules_SessionLocal
from app.models.skill_config import ReasoningNodeDefault

DEFAULT_SKILL_KEY = "requirement_analysis"

# 需求分析节点默认契约：只描述结构（产物/开关/数据源），提示词文案不在此。
DEFAULT_REASONING_NODE_CONTRACT: dict = json.loads(r'''{
  "input": {
    "output_artifact": "requirement_text",
    "deterministic": true
  },
  "agent_fill": {
    "output_artifact": "ext / requirement",
    "data_sources": ["server_catalog", "demand_analysis_docs"],
    "rule_types": ["platform_series_map", "category_alias", "workload_map",
                   "compliance_map", "gpu_form_map", "type_package"],
    "conflict_strategy": "auto_resolve"
  },
  "model_reason": {
    "output_artifact": "baselines / model_selection",
    "wiring": {
      "result_tool": "choose_model",
      "result_selected_key": "selected",
      "result_id_key": "model_id",
      "result_name_key": "name",
      "result_pool_key": "baselines_pool",
      "pool_id_keys": ["server_model_id", "id"],
      "pool_name_key": "name",
      "default_reason": "AI 按需求在候选池内选定",
      "lock_handler": "lock_baseline",
      "progress_handler": "save_scheme_progress"
    }
  },
  "kp_reason": {
    "output_artifact": "kp_parts / kp_by_model"
  },
  "compose": {
    "kp_source": "per_baseline",
    "psu_override_enabled": true,
    "psu_wattage_source": "ext.psu.wattage",
    "psu_qty_source": "ext.psu.qty",
    "deterministic": true
  },
  "output": {
    "output_artifact": "bom_scheme_draft",
    "output_kind": "bom_scheme_draft",
    "payload_map": {"plans": "ctx.plans", "ext": "ctx.ext"},
    "deterministic": true
  }
}''')


# 节点产物槽针脚（目标层插头）：默认契约的一部分。
# 「哪个节点的产物装进哪个槽」是**配置**（此处 = 空库初始配置），不是代码逻辑：
# 运行时只认节点配置里的 target.artifacts[0].slot（见 skill_node_artifacts.resolve_kind），
# 这里只是这本配置的初始值；改画布抽屉即可覆盖，代码零改动。
NODE_PLUGS: dict = {
    "input": {"slot": "requirement_text", "name": "需求原文", "kind": "document",
              "rows_from": "requirement_text"},
    "agent_fill": {"slot": "requirement_slots", "name": "线索登记表", "kind": "form",
                   "view": "requirement_sheet", "rows_from": "requirement_slots"},
    "model_reason": {"slot": "l6_chassis", "name": "机箱表（L6 配置）", "kind": "table",
                     "schema_ref": "plan_config", "view": "plan_l6", "rows_from": "template_eval"},
    "kp_reason": {"slot": "kp_table", "name": "配件表（方案配置配件部分）", "kind": "table",
                  "schema_ref": "plan_config", "view": "plan_kp", "rows_from": "kp_landing"},
    "compose": {"slot": "plans", "name": "方案配置表（L6 + KP 组装结果）", "kind": "table",
                "rows_from": "bom_excel_rows",
                "columns": [
                    {"key": "part_category", "label": "Catalogue", "from": "part_category",
                     "fallback": "category"},
                    {"key": "catalogue", "label": "Configuration Description", "from": "catalogue",
                     "fallback": "name"},
                    {"key": "qty", "label": "Quantity", "from": "qty", "fallback": "1"}]},
    "output": {"slot": "bom_scheme", "name": "方案配置卡", "kind": "table",
               "rows_from": "output_payload"},
}


def tools_for_node(node_key: str) -> list:
    """节点默认工具集：唯一真源 = capability_spec（节点能力声明），此处不另写清单。"""
    from app.services.capability_spec import default_tools
    try:
        return list(default_tools(str(node_key or "").strip()))
    except KeyError:
        return []


def plug_with_slot(node_key: str, cfg: dict) -> dict:
    """把产物槽针脚并进节点配置（保留既有 name/kind/columns，只补 slot）。"""
    plug = NODE_PLUGS.get(str(node_key or "").strip())
    if not plug:
        return dict(cfg or {})
    out = dict(cfg or {})
    target = out.get("target")
    tgt = dict(target) if isinstance(target, dict) else {}
    arts = [dict(a) for a in (tgt.get("artifacts") or []) if isinstance(a, dict)]
    if arts and str(arts[0].get("slot") or "").strip() == plug["slot"]:
        return out
    arts = [{**plug, **arts[0], "slot": plug["slot"]}] if arts else [dict(plug)]
    tgt["artifacts"] = arts
    out["target"] = tgt
    return out


def ensure_reasoning_node_defaults(session=None) -> int:
    """空库时按 DEFAULT_REASONING_NODE_CONTRACT 播种；已有的行不覆盖。返回新建行数。"""
    own = session is None
    s = session or Rules_SessionLocal()
    created = 0
    try:
        now = datetime.now().isoformat()
        for node_key, cfg in DEFAULT_REASONING_NODE_CONTRACT.items():
            exists = s.query(ReasoningNodeDefault).filter(
                ReasoningNodeDefault.skill_key == DEFAULT_SKILL_KEY,
                ReasoningNodeDefault.node_key == node_key,
            ).first()
            if exists:
                continue
            seed_cfg = dict(cfg or {})
            seed_cfg["enabled_tools"] = tools_for_node(str(node_key))
            s.add(ReasoningNodeDefault(
                skill_key=DEFAULT_SKILL_KEY,
                node_key=str(node_key),
                config=json.dumps(plug_with_slot(str(node_key), seed_cfg), ensure_ascii=False),
                version=1,
                updated_at=now,
                updated_by="bootstrap",
            ))
            created += 1
        if created:
            s.commit()
    finally:
        if own:
            s.close()
    return created


def ensure_node_wiring_backfill(session=None) -> int:
    """存量行补 wiring（方案一迁移，幂等，带 guard）：默认行缺 wiring 段 → 按种子补上。

    只补缺（已有 wiring 的行原样跳过），种子值 = 原 _ModelNode 类属性逐字迁移 →
    迁移零行为变化。返回更新行数。
    """
    own = session is None
    s = session or Rules_SessionLocal()
    updated = 0
    try:
        now = datetime.now().isoformat()
        for node_key, cfg in DEFAULT_REASONING_NODE_CONTRACT.items():
            wiring = (cfg or {}).get("wiring")
            if not wiring:
                continue
            row = s.query(ReasoningNodeDefault).filter(
                ReasoningNodeDefault.skill_key == DEFAULT_SKILL_KEY,
                ReasoningNodeDefault.node_key == node_key,
            ).first()
            if row is None:
                continue
            try:
                cur = json.loads(row.config or "{}")
            except Exception:
                cur = {}
            if not isinstance(cur, dict) or cur.get("wiring"):
                continue
            cur["wiring"] = dict(wiring)
            row.config = json.dumps(cur, ensure_ascii=False)
            row.updated_at = now
            row.updated_by = "wiring_backfill"
            updated += 1
        if updated:
            s.commit()
    finally:
        if own:
            s.close()
    return updated
