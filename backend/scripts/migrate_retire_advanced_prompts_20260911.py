# -*- coding: utf-8 -*-
"""「提示词（高级）」整块退役（2026-09-11，一次性；可重复执行）。

用户裁定：角色层不再有第二个提示词桶。删除 rules.system_config.ai_colleagues.value.behavior 下：
  brain.system_prompt / brain.user_rule / brain.minutes_prompt
  mission.agent_system_prompt / mission.lead_system_prompt
  charter（整块：handoff / workflow_list / chat_default / tool_usage / dispatch_judge / memory_extract）

运行期唯一提示词出处 = 员工自身提示词（Manage Teams · 员工）+ Skill Studio 左栏（任务规则/节点抽屉）。
幂等：跑第二遍 changed=0。用法（backend 目录）：python -X utf8 scripts/migrate_retire_advanced_prompts_20260911.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

SCALARS = [
    ("brain", "system_prompt"),
    ("brain", "user_rule"),
    ("brain", "minutes_prompt"),
    ("mission", "agent_system_prompt"),
    ("mission", "lead_system_prompt"),
]


def main() -> int:
    changed = 0
    with ENG.begin() as conn:
        row = conn.execute(sa.text(
            "SELECT value FROM rules.system_config WHERE key='ai_colleagues'"
        )).fetchone()
        if not row:
            print("ai_colleagues 不存在，无事可做")
            return 0
        cfg = row[0]
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        if not isinstance(cfg, dict):
            print("配置不是 dict，跳过")
            return 0
        behavior = cfg.get("behavior")
        if not isinstance(behavior, dict):
            print("behavior 不存在，无事可做")
            return 0
        for section, key in SCALARS:
            node = behavior.get(section)
            if isinstance(node, dict) and key in node:
                node.pop(key)
                changed += 1
                print("删除 behavior.%s.%s" % (section, key))
        if "charter" in behavior:
            behavior.pop("charter")
            changed += 1
            print("删除 behavior.charter（整块）")
        if changed:
            conn.execute(sa.text(
                "UPDATE rules.system_config SET value=:v WHERE key='ai_colleagues'"
            ), {"v": json.dumps(cfg, ensure_ascii=False)})
    print("changed =", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
