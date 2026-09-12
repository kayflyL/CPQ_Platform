# -*- coding: utf-8 -*-
"""A/C/B 程序前置备份：把将被改动的 rules.* 表导出 JSON。一次性脚本。"""
import json
import os
from sqlalchemy import create_engine, text

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_backup_ACB_20260912")
os.makedirs(OUT_DIR, exist_ok=True)

eng = create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)


def dump(name: str, sql: str) -> None:
    with eng.connect() as cn:
        rows = [dict(r._mapping) for r in cn.execute(text(sql))]
    path = os.path.join(OUT_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    print(f"{name}: {len(rows)} rows -> {path}")


dump("reasoning_node_default", "SELECT node_key, config, updated_at FROM rules.reasoning_node_default ORDER BY node_key")
dump("reasoning_flow_125", "SELECT id, name, is_active, graph FROM rules.reasoning_flow WHERE id = 125")
dump("reasoning_node_config", "SELECT flow_id, node_key, config, updated_at FROM rules.reasoning_node_config WHERE flow_id = 125 ORDER BY node_key")
dump("compatibility_rules", "SELECT * FROM rules.compatibility_rules ORDER BY id")
dump("derivation_rules", "SELECT * FROM rules.derivation_rules ORDER BY id")
