"""目标层插头迁移（2026-09-06，幂等）：

背景：kp_reason/model_reason 的目标层描述符与资源层是"样子货"——
  ① columns 无 from/fallback 产源映射 → 执行器行键硬编码，改描述符不生效；
  ② 默认契约 reasoning_node_default 里挂着旧内核死工具（select_parts/compose_memory 等），
     资源层抽屉展示的是死工具，实际大脑硬编码跑 select_kp_parts/ask_user；
  ③ 工具真源未落 DB。

动作（幂等，可重复执行）：
  A. reasoning_node_default（requirement_analysis）kp_reason/model_reason 行重写为当前契约：
     enabled_tools=当前真实工具集；target.artifacts[0].columns 带 from/fallback；
     清掉旧内核死键（system_prompt/rule_types/series_limit/intro_length/sort_by/…）。
  B. reasoning_node_config（active 流）同名节点：target.artifacts[0].columns 补 from/fallback
     （值=现硬编码映射，行为零变化）；不动其他键。
  C. system_config 写 kp_category_aliases（类目别名→库内真实类目，只映射真实存在的类目）。
"""
import json
import sys

import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

# 现硬编码行键 → 产源映射（行为零变化的权威出处：skill_plan_runtime kp 段 / plan_builder）
KP_COLUMNS = [
    {"key": "part_category", "label": "Catalogue", "visible": True,
     "from": "category", "fallback": "category"},
    {"key": "catalogue", "label": "Configuration Description", "visible": True,
     "from": "name", "fallback": "request_spec|category"},
    {"key": "qty", "label": "Quantity", "visible": True,
     "from": "qty", "fallback": "1"},
]
L6_COLUMNS = [
    {"key": "catalogue", "label": "配置件", "visible": True,
     "from": "catalogue", "fallback": ""},
    {"key": "description", "label": "说明", "visible": True,
     "from": "description", "fallback": ""},
    {"key": "qty", "label": "数量", "visible": True,
     "from": "qty", "fallback": "1"},
]

def kp_target():
    return {
        "kind": "sheet_section", "view": "plan_kp", "schema_ref": "plan_config",
        "note": "方案配置表对应部分",
        "artifacts": [{
            "name": "配件表（方案配置配件部分）", "kind": "table",
            "schema_ref": "plan_config", "view": "plan_kp", "rows_from": "kp_landing",
            "note": "方案配置表配件部分 · 3 列同商机方案配置表（Catalogue/Configuration Description/Quantity）",
            "columns": KP_COLUMNS,
        }],
    }

def model_target():
    return {
        "kind": "sheet_section", "view": "plan_l6", "schema_ref": "plan_config",
        "note": "方案配置表对应部分",
        "artifacts": [{
            "name": "机箱表（L6 配置）", "kind": "table",
            "schema_ref": "plan_config", "view": "plan_l6", "rows_from": "template_eval",
            "note": "方案配置表 L6 部分 · 来源：该机型 BOM 模板求值（基础机箱）",
            "columns": L6_COLUMNS,
        }],
    }

# 默认契约（reasoning_node_default）：只留当前内核真实消费的键
DEFAULTS = {
    "kp_reason": {
        "description": "AI 按登记行语义从该行候选池锁定库内真实料号；池外拒绝、空池如实说明",
        "enabled_tools": ["select_kp_parts", "ask_user"],
        "target": kp_target(),
    },
    "model_reason": {
        "description": "按线索登记信号从候选机型池锁定在售机型；池外拒绝，无法决断交客户",
        "enabled_tools": ["select_model"],
        "target": model_target(),
    },
}

# 类目别名（只映射库内真实类目；电源等库内没有的类目不映射，由大脑如实说明）
ALIASES = {
    "网卡": "NIC", "网卡适配器": "NIC", "网络适配器": "NIC", "万兆网卡": "NIC",
    "硬盘": "HDD/SSD", "固态硬盘": "HDD/SSD", "机械硬盘": "HDD/SSD",
    "内存": "Memory", "内存条": "Memory",
    "阵列卡": "Raid card", "RAID卡": "Raid card",
    "显卡": "GPU", "GPU卡": "GPU", "加速卡": "GPU",
}

def cols_with_mapping(art: dict) -> dict:
    """给已有 columns 补 from/fallback（幂等：已带 from 的不动）。"""
    arts = ((art or {}).get("artifacts") or [])
    for a in arts:
        cols = a.get("columns") or []
        for c in cols:
            if isinstance(c, dict) and not c.get("from"):
                m = next((x for x in KP_COLUMNS + L6_COLUMNS if x["key"] == c.get("key")), None)
                if m:
                    c["from"] = m["from"]
                    c.setdefault("fallback", m["fallback"])
    return art

def main() -> int:
    with ENG.begin() as c:
        # A. 默认契约行重写（幂等：整行覆盖为当前契约）
        for node_key, contract in DEFAULTS.items():
            row = c.execute(sa.text(
                "SELECT id, config FROM rules.reasoning_node_default "
                "WHERE skill_key='requirement_analysis' AND node_key=:k"),
                {"k": node_key}).first()
            if row is None:
                c.execute(sa.text(
                    "INSERT INTO rules.reasoning_node_default "
                    "(skill_key, node_key, config, updated_at, updated_by) "
                    "VALUES ('requirement_analysis', :k, :cfg, NOW(), 'migrate-target-contract')"),
                    {"k": node_key, "cfg": json.dumps(contract, ensure_ascii=False)})
                print(f"[default] {node_key}: inserted")
            else:
                cfg = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
                contract = dict(contract)
                contract["target"] = cols_with_mapping(contract["target"])
                cfg.clear()
                cfg.update(contract)
                c.execute(sa.text(
                    "UPDATE rules.reasoning_node_default SET config=:cfg, updated_by='migrate-target-contract' "
                    "WHERE id=:i"), {"cfg": json.dumps(cfg, ensure_ascii=False), "i": row[0]})
                print(f"[default] {node_key}: rewritten (keys={sorted(cfg.keys())})")

        # B. active 流实例配置：columns 补映射（幂等）
        flow = c.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow "
            "WHERE skill_key='requirement_analysis' AND is_active ORDER BY id DESC LIMIT 1")).first()
        if flow is None:
            print("[config] no active flow, skip")
            return 0
        rows = c.execute(sa.text(
            "SELECT node_key, config FROM rules.reasoning_node_config WHERE flow_id=:f"),
            {"f": flow[0]}).fetchall()
        for node_key, raw in rows:
            if node_key not in DEFAULTS:
                continue
            cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
            before = json.dumps(cfg.get("target"), ensure_ascii=False)
            cfg["target"] = cols_with_mapping(cfg.get("target") or DEFAULTS[node_key]["target"])
            after = json.dumps(cfg.get("target"), ensure_ascii=False)
            if before != after:
                c.execute(sa.text(
                    "UPDATE rules.reasoning_node_config SET config=:cfg, updated_by='migrate-target-contract' "
                    "WHERE flow_id=:f AND node_key=:k"),
                    {"cfg": json.dumps(cfg, ensure_ascii=False), "f": flow[0], "k": node_key})
                print(f"[config] flow={flow[0]} {node_key}: columns mapping added")
            else:
                print(f"[config] flow={flow[0]} {node_key}: already mapped")

        # C. 类目别名 → system_config（幂等：存在则跳过，尊重手工改动）
        cur = c.execute(sa.text(
            "SELECT value FROM rules.system_config WHERE key='kp_category_aliases'")).first()
        if cur is None:
            c.execute(sa.text(
                "INSERT INTO rules.system_config (key, value, type, updated_by) "
                "VALUES ('kp_category_aliases', :v, 'json', 'migrate-target-contract')"),
                {"v": json.dumps(ALIASES, ensure_ascii=False)})
            print(f"[aliases] inserted {len(ALIASES)} entries")
        else:
            print("[aliases] exists, keep")
    print("DONE")
    return 0

if __name__ == "__main__":
    sys.exit(main())
