# -*- coding: utf-8 -*-
"""提示词清理（2026-09-11，一次性；可重复执行）。

背景：AGENT_PROTOCOL 等代码常量曾把「机制约定」写成系统提示词注入，与左栏（Skill Studio）
形成第二套提示词。代码侧已删除；本脚本收尾 DB：
  1) 把原协议第 3 条（对客户只说确认+问题）并入左栏「使用说明」manual_rules（唯一可编辑提示词处）；
  2) 删掉 reasoning_node_default.agent_fill 里已废弃的旧键 prompt（界面早已不读、_legacy_node_keys 会剥）。
只动这两处，其余原样保留；幂等。

用法（backend 目录）：python -X utf8 scripts/migrate_prompt_cleanup_20260911.py
"""
import json
import sys

import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

SKILL_KEY = "requirement_analysis"
RULE_17 = ("17. 你对客户说的话只包含两样：已完成事项的简短确认、需要客户决策的问题。"
           "内部推理、工具调用细节、系统返回原文一律不得写进对客户的话。")


def main() -> int:
    changed = 0
    with ENG.begin() as c:
        fid = c.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow WHERE skill_key=:s AND is_active IS TRUE"
            " ORDER BY id DESC LIMIT 1"), {"s": SKILL_KEY}).scalar()
        if fid is None:
            print("[flow] no active flow, skip")
        else:
            raw = c.execute(sa.text("SELECT graph FROM rules.reasoning_flow WHERE id=:i"),
                            {"i": fid}).scalar()
            g = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            mr = str(g.get("manual_rules") or "")
            if "内部推理、工具调用细节" in mr:
                print("[flow] rule 17 already present")
            else:
                g["manual_rules"] = (mr.rstrip() + "\n" + RULE_17) if mr.strip() else RULE_17
                c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                          {"g": json.dumps(g, ensure_ascii=False), "i": fid})
                print("[flow] manual_rules += rule 17 (now %d chars)" % len(g["manual_rules"]))
                changed += 1

        row = c.execute(sa.text(
            "SELECT id, config FROM rules.reasoning_node_default"
            " WHERE skill_key=:s AND node_key='agent_fill'"), {"s": SKILL_KEY}).first()
        if row is None:
            print("[default] agent_fill row missing, skip")
        else:
            cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            if "prompt" in cfg:
                cfg.pop("prompt", None)
                c.execute(sa.text(
                    "UPDATE rules.reasoning_node_default SET config=:c,"
                    " updated_by='prompt-cleanup' WHERE id=:i"),
                    {"c": json.dumps(cfg, ensure_ascii=False), "i": row[0]})
                print("[default] agent_fill.prompt removed")
                changed += 1
            else:
                print("[default] agent_fill.prompt already absent")
    print("DONE changed=%d" % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
