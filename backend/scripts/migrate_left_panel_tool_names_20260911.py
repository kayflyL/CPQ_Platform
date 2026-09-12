# -*- coding: utf-8 -*-
"""左栏/配置层旧工具名归一（2026-09-11，一次性；可重复执行）。

背景：工具名归一（tool_names.TOOL_RENAME_MAP / RETIRED_TOOL_IDS）只在**读取**时生效，
DB 配置里仍躺着旧名 —— 左栏提示词（manual_rules / 节点抽屉）与角色 tool_ids 会对大脑
说一套不存在的工具名（P5 盘点实测：manual_rules 14/15 条、model_reason 抽屉、
system_config 的 4 个角色）。本脚本把配置层**就地**对齐到现行名，使读取期 shim 将来可退役。

只改「配置面」，绝不碰历史：
  ✅ rules.reasoning_flow.graph（manual_rules / 节点 manual_rules / description）
  ✅ rules.reasoning_node_default.config
  ✅ rules.reasoning_node_config.config
  ✅ rules.system_config.value 里 role 的 tool_ids 列表（递归）
  ❌ opportunities.assistant_threads.reasoning_state（历史回合记录，原样保留）

幂等：跑两遍第二遍 changed=0。用法（backend 目录）：
  python -X utf8 scripts/migrate_left_panel_tool_names_20260911.py
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

# 正文里的旧名替换（工具名 → 现行名）。begin_step 是已废除的机制工具：句子改述。
TEXT_RENAMES = [
    ("select_models", "choose_model"),
    ("select_model", "choose_model"),
    ("search_kp_parts", "query_parts"),
    ("select_kp_parts", "select_parts"),
    ("pick_kp_parts", "select_parts"),
    ("choose_parts", "select_parts"),
    ("spec_filters", "required_specs"),
    ("open_part", "inspect_parts(action=part)"),
    ("open_row", "inspect_parts(action=row)"),
    ("open_category", "inspect_parts(action=category)"),
    ("grep_parts", "inspect_parts(action=grep)"),
    ("begin_step 后", ""),
    ("begin_step后", ""),
    ("begin_step", ""),
    ("end_step", ""),
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
    """递归改文案 + 归一 tool_ids 列表；返回值与原值比较后由调用方决定是否落库。"""
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
        for row in c.execute(sa.text(
                "SELECT id, graph FROM rules.reasoning_flow")).fetchall():
            g = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            new = walk(g, "flow:%s" % row[0])
            if json.dumps(new, ensure_ascii=False, sort_keys=True) != \
                    json.dumps(g, ensure_ascii=False, sort_keys=True):
                if not DRY:
                    c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                              {"g": json.dumps(new, ensure_ascii=False), "i": row[0]})
                _state["changed"] += 1

        for tbl in ("reasoning_node_default", "reasoning_node_config"):
            for row in c.execute(sa.text(
                    "SELECT id, config FROM rules.%s" % tbl)).fetchall():
                cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
                new = walk(cfg, "%s:%s" % (tbl, row[0]))
                if json.dumps(new, ensure_ascii=False, sort_keys=True) != \
                        json.dumps(cfg, ensure_ascii=False, sort_keys=True):
                    if not DRY:
                        c.execute(sa.text(
                            "UPDATE rules.%s SET config=:c, updated_by='tool-name-fix' WHERE id=:i" % tbl),
                            {"c": json.dumps(new, ensure_ascii=False), "i": row[0]})
                    _state["changed"] += 1

        for row in c.execute(sa.text(
                "SELECT key, value FROM rules.system_config WHERE value IS NOT NULL")).fetchall():
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
            if json.dumps(new, ensure_ascii=False, sort_keys=True) != \
                    json.dumps(parsed, ensure_ascii=False, sort_keys=True):
                if not DRY:
                    c.execute(sa.text("UPDATE rules.system_config SET value=:v WHERE key=:k"),
                              {"v": json.dumps(new, ensure_ascii=False), "k": row[0]})
                _state["changed"] += 1

    print("DONE rows_changed=%d dry=%s" % (_state["changed"], DRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
