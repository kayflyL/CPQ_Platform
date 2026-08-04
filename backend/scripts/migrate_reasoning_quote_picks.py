#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""存量修复：推理流（source=reasoning）转出的报价单丢了服务器型号与 IO 选配。

背景（2026-08-05 恶性 BUG）：
  - plan.model 用了 base_config.model（基准配置名）而非 server_models.name（服务器型号）
    → config_server_models 填成基准配置名，机箱卡按 server_model_id 匹配不到目录机型，
      形态/用途全空；
  - config_l6_picks 未持久化 server_model_id 与 IO 选配（picks.rear）
    → 机箱配置器 IO1/IO2 数量 0（BOM 单有 IO 行、配置器没配）。

本脚本幂等（可重复跑）：
  1) config_server_models 修正为服务器型号名（按 base_config_id → model_id 反查，或按现名匹配）；
  2) config_l6_picks[cfg] 补 server_model_id；
  3) config_l6_picks[cfg].picks.rear 按机型标准 riser（config_content.standard_riser）+ 默认组合槽兜底填充，
     与推理 BOM 左栏 IO 行同源（1*X8 → ['x8']，1*X16+1*X8 → ['x16','x8']，OCP 默认 ocp_x8）。
用法（backend 目录）：python -X utf8 scripts/migrate_reasoning_quote_picks.py
"""
import sys
import os
import json

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sqlalchemy import text
from app.models.base import engine

# rear-io 选项（option_type 清单）按系列桶
def load_rear_options(conn):
    rows = conn.execute(text(
        "SELECT io_slot, option_type FROM l6.l6_rear_panel_items"
    )).mappings().all()
    opts: dict[str, set] = {}
    for r in rows:
        opts.setdefault(r["io_slot"], set()).add(r["option_type"])
    return {k: [o for o in v if o != "blank"] for k, v in opts.items()}


def option_types_from_riser_desc(desc):
    """'1*X8 FHFL' -> ['x8']；'1*X16+1*X8 FHFL' -> ['x16','x8']"""
    if not desc:
        return []
    out = []
    import re
    for m in re.finditer(r"(\d+)\s*\*\s*(X16|X8)", str(desc), re.I):
        qty = int(m.group(1))
        t = m.group(2).lower()
        out.extend([t] * qty)
    return out


def std_riser_for_slot(std, slot):
    if isinstance(std, dict):
        if std.get(slot):
            return std[slot]
        k = next((x for x in std if str(x).lower() == str(slot).lower()), None)
        return (k and std.get(k)) or std.get("default")
    return std or None


def default_rear_from(slot_defs, options):
    """组合槽(IO1/IO2)默认 1×X16+1×X8、OCP 默认 X8；其余槽挡片（与前端 defaultRearFrom 同逻辑）。"""
    out = {}
    combo = {"IO1", "IO2"}
    for s in slot_defs or []:
        opts = [o for o in (options.get(s["name"]) or []) if o != "blank"]
        if not opts:
            continue
        if s["name"] == "OCP":
            out[s["name"]] = ["ocp_x8"] if "ocp_x8" in opts else [opts[0]]
        elif s["name"] in combo:
            has16 = "x16" in opts
            has8 = "x8" in opts
            out[s["name"]] = ["x16", "x8"] if (has16 and has8) else [opts[0]]
    return out


def rear_for_plan(slot_defs, std_riser, options):
    """推理 BOM 的 IO 选配：标准 riser 优先（与 BOM 左栏同源），未配置槽位兜底默认组合槽/OCP。"""
    out = {}
    for s in slot_defs or []:
        types = option_types_from_riser_desc(std_riser_for_slot(std_riser, s["name"]))
        if types:
            out[s["name"]] = types
    for slot, opts in default_rear_from(slot_defs, options).items():
        out.setdefault(slot, opts)
    return out


def main():
    stats = {"scanned": 0, "fixed_server_model": 0, "fixed_picks": 0, "skipped_no_base": 0}
    with engine.connect() as conn:
        # 机型表 + 基准配置表（model_id 反向关联）
        models = {r["id"]: r["name"] for r in conn.execute(text(
            "SELECT id, name FROM l6.server_models"
        )).mappings().all()}
        bcs = {r["id"]: dict(r) for r in conn.execute(text(
            "SELECT id, model_id, config_content, rear_slots FROM l6.base_configs"
        )).mappings().all()}
        rear_opts = load_rear_options(conn)

        qs = conn.execute(text("""
            SELECT quotation_id, quotation_name, config_server_models, extra_fields
            FROM opportunities.quotations
            WHERE source = 'reasoning'
               OR extra_fields::text ILIKE '%config_l6_picks%'
            ORDER BY created_at DESC
        """)).mappings().all()

        for q in qs:
            stats["scanned"] += 1
            csm = dict(q["config_server_models"] or {})
            ef_raw = q["extra_fields"] or "{}"
            try:
                ef = json.loads(ef_raw) if isinstance(ef_raw, str) else dict(ef_raw or {})
            except Exception:
                ef = {}
            picks = dict(ef.get("config_l6_picks") or {})

            changed_csm = False
            changed_picks = False
            for cfg_name, cfg in picks.items():
                cfg = dict(cfg or {})
                bc = bcs.get(cfg.get("base_config_id")) or {}
                if not bc:
                    stats["skipped_no_base"] += 1
                    continue
                # 1) server_model_id：已有 > 反查 base_config.model_id
                smid = cfg.get("server_model_id")
                if not smid and bc.get("model_id"):
                    smid = bc["model_id"]
                if smid:
                    # 1b) server_model_id 也在 config_l6_picks 里，修改需落库 extra_fields
                    if cfg.get("server_model_id") != smid:
                        cfg["server_model_id"] = smid
                        changed_picks = True
                    # 2) config_server_models 修正为服务器型号名
                    sm_name = models.get(smid)
                    old_name = csm.get(cfg_name)
                    if sm_name and old_name != sm_name:
                        csm[cfg_name] = sm_name
                        changed_csm = True
                # 3) picks.rear：标准 riser 优先 + 默认组合槽兜底（与推理 BOM 左栏 IO 行同源）
                if "rear" not in (cfg.get("picks") or {}):
                    slot_defs = bc.get("rear_slots") or [
                        {"name": "IO1", "cap": 3}, {"name": "IO2", "cap": 3},
                        {"name": "IO3", "cap": 3}, {"name": "IO4", "cap": 3}, {"name": "OCP", "cap": 1},
                    ]
                    std_riser = (bc.get("config_content") or {}).get("standard_riser")
                    rear = rear_for_plan(slot_defs, std_riser, rear_opts)
                    sub = dict(cfg.get("picks") or {})
                    sub["rear"] = rear
                    cfg["picks"] = sub
                    changed_picks = True
                picks[cfg_name] = cfg

            if changed_picks:
                ef["config_l6_picks"] = picks
            if changed_csm or changed_picks:
                with engine.begin() as w:
                    if changed_csm:
                        w.execute(text(
                            "UPDATE opportunities.quotations SET config_server_models = :csm WHERE quotation_id = :qid"
                        ), {"csm": json.dumps(csm, ensure_ascii=False), "qid": q["quotation_id"]})
                    if changed_picks:
                        w.execute(text(
                            "UPDATE opportunities.quotations SET extra_fields = :ef WHERE quotation_id = :qid"
                        ), {"ef": json.dumps(ef, ensure_ascii=False), "qid": q["quotation_id"]})
                if changed_csm:
                    stats["fixed_server_model"] += 1
                if changed_picks:
                    stats["fixed_picks"] += 1
                print(f"  ✓ {q['quotation_id']}  {q['quotation_name'] or ''}"
                      f"{' [型号]' if changed_csm else ''}{' [IO/型号id]' if changed_picks else ''}")
            else:
                print(f"  - {q['quotation_id']}  无需修复")

    print(f"\n完成：扫描 {stats['scanned']} 单，修型号 {stats['fixed_server_model']} 单，修 picks {stats['fixed_picks']} 单，跳过 {stats['skipped_no_base']} 配置")


if __name__ == "__main__":
    main()
