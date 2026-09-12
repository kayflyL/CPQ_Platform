# -*- coding: utf-8 -*-
"""幂等迁移：kp_reason「必须反问」类目 + 登记策略 kp_required。

背景（2026-09-07 AI=配置器）：配件选配节点不允许软开「AI 反问」，改为「必须反问」——
CPU/Memory/HDD-SSD/Raid card/NIC/GPU 由大脑给候选+推荐并交客户确认（含自选/数量），
其他类目（Bridge/HBA/NVSwitch）仍由 AI 代选。这里把 active 流 + 默认契约的
kp_reason target.artifacts[0].fields 写为每类一行、ask=true；并把登记策略
requirement_slots.kp_required 设为 5 个必登记大类（GPU 可选）。

用法（backend 目录）：.\.venv\Scripts\python.exe -X utf8 scripts/migrate_kp_must_ask.py
"""
import json
import sys

import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

MUST_ASK = ["CPU", "Memory", "HDD/SSD", "Raid card", "NIC", "GPU"]
KP_REQUIRED = ["CPU", "Memory", "HDD/SSD", "Raid card", "NIC"]


def _kp_categories(c):
    try:
        rows = c.execute(sa.text(
            "SELECT name FROM kp.kp_categories ORDER BY sort_order, id")).mappings().all()
        return [str(r["name"]).strip() for r in rows if r.get("name")]
    except Exception:
        return []


def _fields_for(categories):
    seen, out = set(), []
    for name in categories:
        if name in seen:
            continue
        seen.add(name)
        out.append({
            "key": f"kp_parts:{name}", "label": name,
            "hint": "配件行 · 必填=该行必须落在最终方案；客户已明确登记具体型号→AI 直接锁定；未登记/仅类目名→AI 推荐并调 ask_user 确认（含自选/数量）；关=非必填，AI 可选配",
            "group": "部件行 · 本节点要填的配件",
            "ask": name in MUST_ASK,
        })
    return out


def _set_fields(art, categories):
    arts = art.get("artifacts") or []
    for a in arts:
        if (a.get("view") or "") != "plan_kp":
            continue
        existing = {}
        for f in (a.get("fields") or []):
            if isinstance(f, dict) and str(f.get("key") or "").startswith("kp_parts:"):
                existing[str(f["key"]).split(":", 1)[1].strip()] = f
        merged = []
        for name in categories:
            f = existing.get(name)
            if not isinstance(f, dict):
                f = {"key": f"kp_parts:{name}", "label": name,
                     "hint": "配件行 · 必填=该行必须落在最终方案；客户已明确登记具体型号→AI 直接锁定；未登记/仅类目名→AI 推荐并调 ask_user 确认（含自选/数量）；关=非必填，AI 可选配",
                     "group": "部件行 · 本节点要填的配件"}
            f["ask"] = name in MUST_ASK
            f.setdefault("key", f"kp_parts:{name}")
            f.setdefault("label", name)
            merged.append(f)
        a["fields"] = merged
    return art


def main() -> int:
    cats = None
    with ENG.begin() as c:
        cats = _kp_categories(c)
        # A. 默认契约
        rows = c.execute(sa.text(
            "SELECT id, config FROM rules.reasoning_node_default "
            "WHERE skill_key='requirement_analysis' AND node_key='kp_reason'")).fetchall()
        for row in rows:
            cfg = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
            _set_fields(cfg.get("target") or {}, cats)
            c.execute(sa.text("UPDATE rules.reasoning_node_default SET config=:cfg, updated_by='migrate-kp-must-ask' "
                              "WHERE id=:i"), {"cfg": json.dumps(cfg, ensure_ascii=False), "i": row[0]})
            print(f"[default] kp_reason: must_ask fields set ({len(cats)} cats)")

        # B. active 流实例
        flow = c.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow "
            "WHERE skill_key='requirement_analysis' AND is_active ORDER BY id DESC LIMIT 1")).first()
        if flow is not None:
            default_cfg = None
            for node_key, raw in c.execute(sa.text(
                    "SELECT node_key, config FROM rules.reasoning_node_config WHERE flow_id=:f"),
                    {"f": flow[0]}).fetchall():
                if node_key != "kp_reason":
                    continue
                cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
                if not cfg.get("target"):
                    # active 为空/无 target → 用默认契约作为基底再补 must_ask 字段
                    if default_cfg is None:
                        drow = c.execute(sa.text(
                            "SELECT config FROM rules.reasoning_node_default "
                            "WHERE skill_key='requirement_analysis' AND node_key='kp_reason'")).first()
                        default_cfg = json.loads(drow[0]) if drow and isinstance(drow[0], str) else (drow[0] if drow else {})
                    cfg = dict(default_cfg)
                    seeded = True
                else:
                    seeded = False
                before = json.dumps(((cfg.get("target") or {}).get("artifacts") or [{}])[0].get("fields") or [], ensure_ascii=False)
                _set_fields(cfg.get("target") or {}, cats)
                after = json.dumps(((cfg.get("target") or {}).get("artifacts") or [{}])[0].get("fields") or [], ensure_ascii=False)
                if seeded or before != after:
                    c.execute(sa.text(
                        "UPDATE rules.reasoning_node_config SET config=:cfg, updated_by='migrate-kp-must-ask' "
                        "WHERE flow_id=:f AND node_key=:k"),
                        {"cfg": json.dumps(cfg, ensure_ascii=False), "f": flow[0], "k": node_key})
                    print(f"[config] flow={flow[0]} kp_reason: must_ask fields set")
                else:
                    print(f"[config] flow={flow[0]} kp_reason: already set")

        # C. 登记策略 kp_required（保留其他键，只覆盖 kp_required）
        row = c.execute(sa.text(
            "SELECT value FROM rules.system_config WHERE key='requirement_slots'")).first()
        val = json.loads(row[0]) if row and isinstance(row[0], str) else (row[0] if row else {})
        if isinstance(val, dict):
            val["kp_required"] = KP_REQUIRED
            val.setdefault("version", 1)
        else:
            val = {"version": 1, "kp_required": KP_REQUIRED}
        if row:
            c.execute(sa.text("UPDATE rules.system_config SET value=:v, updated_by='migrate-kp-must-ask' "
                              "WHERE key=:k"), {"v": json.dumps(val, ensure_ascii=False), "k": "requirement_slots"})
        else:
            c.execute(sa.text(
                "INSERT INTO rules.system_config (key, value, type, updated_by) "
                "VALUES ('requirement_slots', :v, 'json', 'migrate-kp-must-ask')"),
                {"v": json.dumps(val, ensure_ascii=False)})
        print(f"[slots] kp_required set: {KP_REQUIRED}")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
