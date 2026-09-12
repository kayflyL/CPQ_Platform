# -*- coding: utf-8 -*-
"""退役 suggest_parts 的一次性配置层迁移（2026-09-12）。

- enabled_tools/tool_ids 列表走 normalize_tool_ids：suggest_parts 已进入 RETIRED_TOOL_IDS，自动剔除。
- 文本/左栏提示里的 suggest_parts 统一改说成 query_parts，避免大脑被指去调已退役工具。
幂等：跑两遍 changed=0。用法（backend 目录）：
  python -X utf8 scripts/migrate_retire_suggest_parts_20260912.py
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlalchemy as sa

from app.services.tool_names import normalize_tool_ids

DRY = os.environ.get("CPQ_DRY") == "1"

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

TEXT_RENAMES = [
    ("query_parts/suggest_parts", "query_parts"),
    ("suggest_parts", "query_parts"),
    ("query_parts/query_parts", "query_parts"),
]

_state = {"changed": 0}


def fix_text(txt: str, where: str) -> str:
    out = txt
    for old, new in TEXT_RENAMES:
        if old in out:
            out = out.replace(old, new)
            print("  [%s] %r -> %r" % (where, old, new))
    return out


def walk(obj, where: str):
    if isinstance(obj, str):
        return fix_text(obj, where)
    if isinstance(obj, list):
        return [walk(v, where) for v in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("tool_ids", "enabled_tools") and isinstance(v, list):
                norm = normalize_tool_ids([str(x) for x in v])
                if [str(x) for x in v] != norm:
                    print("  [%s] %s %s -> %s" % (where, k, v, norm))
                out[k] = norm
            else:
                out[k] = walk(v, where)
        return out
    return obj


def main() -> int:
    with ENG.begin() as c:
        for row in c.execute(sa.text("SELECT id, graph FROM rules.reasoning_flow")).fetchall():
            g = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            new = walk(g, "flow:%s" % row[0])
            if json.dumps(new, ensure_ascii=False, sort_keys=True) != json.dumps(g, ensure_ascii=False, sort_keys=True):
                if not DRY:
                    c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                              {"g": json.dumps(new, ensure_ascii=False), "i": row[0]})
                _state["changed"] += 1

        for tbl in ("reasoning_node_default", "reasoning_node_config"):
            for row in c.execute(sa.text("SELECT id, config FROM rules.%s" % tbl)).fetchall():
                cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
                new = walk(cfg, "%s:%s" % (tbl, row[0]))
                if json.dumps(new, ensure_ascii=False, sort_keys=True) != json.dumps(cfg, ensure_ascii=False, sort_keys=True):
                    if not DRY:
                        c.execute(sa.text(
                            "UPDATE rules.%s SET config=:c, updated_by='retire-suggest-parts' WHERE id=:i" % tbl),
                            {"c": json.dumps(new, ensure_ascii=False), "i": row[0]})
                    _state["changed"] += 1

        for row in c.execute(sa.text("SELECT key, value FROM rules.system_config WHERE value IS NOT NULL")).fetchall():
            val = row[1]
            parsed = val if isinstance(val, (dict, list)) else None
            if parsed is None:
                try:
                    parsed = json.loads(val or "null")
                except Exception:
                    continue
            if parsed is None:
                continue
            new = walk(parsed, "system_config:%s" % row[0])
            if json.dumps(new, ensure_ascii=False, sort_keys=True) != json.dumps(parsed, ensure_ascii=False, sort_keys=True):
                if not DRY:
                    c.execute(sa.text("UPDATE rules.system_config SET value=:v WHERE key=:k"),
                              {"v": json.dumps(new, ensure_ascii=False), "k": row[0]})
                _state["changed"] += 1

    print("DONE rows_changed=%d dry=%s" % (_state["changed"], DRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
