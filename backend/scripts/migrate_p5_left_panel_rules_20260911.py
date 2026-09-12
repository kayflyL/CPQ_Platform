# -*- coding: utf-8 -*-
"""P5-A 左栏补写（2026-09-11，一次性；可重复执行）。

P5-A 要把代码里那套「怎么做」的句子删干净，删之前先让左栏接住——否则就是能力丢失。
只补三处（都是代码侧正在靠 hint 硬撑、左栏却没有的规则）：

  1) 任务规则 18：按 steps 顺序推进（前置未过校验，end_step 会被引擎拒绝）；
  2) 任务规则 19：推断出来的前提字段（决定配件适用性的类型/系列/形态）必须先经客户选项卡确认；
  3) agent_fill 节点抽屉：目录字段缺口里优先确认「服务器类型」。

幂等：跑第二遍 changed=0。用法（backend 目录）：
  python -X utf8 scripts/migrate_p5_left_panel_rules_20260911.py
  加 CPQ_DRY=1 只打印不落库。
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)
DRY = os.environ.get("CPQ_DRY") == "1"
SKILL_KEY = "requirement_analysis"

RULE_18_OLD = ("18. 严格按 steps 清单顺序推进：前置步骤没过校验，本步的 end_step 会被引擎拒绝"
               "（这是硬校验，不是建议）。")
RULE_18 = ("18. 严格按 steps 清单顺序推进：前置步骤没过校验，本步无法收口推进"
           "（引擎按顺序硬校验，不是建议）。")
RULE_19 = ("19. 决定配件适用性的前提字段（类型/系列/形态）若是你自己推断的（客户没说过），"
           "必须先出选项卡让客户确认，才能进配件选型。")
RULE_20 = ("20. 价格纪律：推荐必须带理由（价格/形态/场景匹配），不知道就去查；引擎明示 "
           "price_access=false（本角色无价格查看权限）时，回复里不出现任何价格/金额/报价数字"
           "（凭记忆编造也不行），客户问价时引导其联系成本核算或方案助手。")
FILL_EXTRA = "目录字段缺口里优先确认「服务器类型」。"

STATE = {"changed": 0}


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def main() -> int:
    with ENG.begin() as c:
        fid = c.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow WHERE skill_key=:s AND is_active IS TRUE"
            " ORDER BY id DESC LIMIT 1"), {"s": SKILL_KEY}).scalar()
        if fid is None:
            print("[flow] 没有生效流程，跳过")
        else:
            raw = c.execute(sa.text("SELECT graph FROM rules.reasoning_flow WHERE id=:i"),
                            {"i": fid}).scalar()
            g = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            mr = str(g.get("manual_rules") or "")
            if RULE_18_OLD in mr:          # 早期措辞点了已退役工具名（end_step），就地换掉
                mr = mr.replace(RULE_18_OLD, RULE_18)
                g["manual_rules"] = mr
                print("[flow:%s] 任务规则 18 措辞修正（去掉已退役工具名）" % fid)
                if not DRY:
                    c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                              {"g": _dump(g), "i": fid})
                STATE["changed"] += 1
            add = [r for r in (RULE_18, RULE_19, RULE_20) if r[:8] not in mr]
            if add:
                g["manual_rules"] = (mr.rstrip() + "\n" + "\n".join(add)) if mr.strip() \
                    else "\n".join(add)
                print("[flow:%s] manual_rules += %d 条 (%d -> %d 字)"
                      % (fid, len(add), len(mr), len(g["manual_rules"])))
                if not DRY:
                    c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                              {"g": _dump(g), "i": fid})
                STATE["changed"] += 1
            else:
                print("[flow:%s] 18/19/20 已在" % fid)

        row = c.execute(sa.text(
            "SELECT id, config FROM rules.reasoning_node_default"
            " WHERE skill_key=:s AND node_key='agent_fill'"), {"s": SKILL_KEY}).first()
        if row is None:
            print("[default] agent_fill 缺失，跳过")
        else:
            cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            desc = str(cfg.get("description") or "")
            if FILL_EXTRA in desc:
                print("[default] agent_fill 抽屉已含该句")
            else:
                cfg["description"] = (desc.rstrip() + FILL_EXTRA)
                print("[default:agent_fill] description += %r" % FILL_EXTRA)
                if not DRY:
                    c.execute(sa.text(
                        "UPDATE rules.reasoning_node_default SET config=:c,"
                        " updated_by='p5-left-panel' WHERE id=:i"),
                        {"c": _dump(cfg), "i": row[0]})
                STATE["changed"] += 1

    print("DONE rows_changed=%d dry=%s" % (STATE["changed"], DRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
