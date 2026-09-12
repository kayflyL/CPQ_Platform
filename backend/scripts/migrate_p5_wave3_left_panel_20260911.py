# -*- coding: utf-8 -*-
"""P5-A 波 3 左栏补写（2026-09-11，一次性；可重复执行）。

波 3 把代码里最后一类「教大脑怎么做」的句子删干净，删之前先让左栏接住：

  任务规则 21：缺口转述话术纪律（skill_chat._transcribe_gap 的注入式系统消息）；
  任务规则 22：引擎「未通过校验」反馈 → 照反馈修正后重试（skill_turn_engine 系统反馈头）；
  任务规则 23：库内确无该料 → 客户在「改平台／换料／保持原需求」拍板（skill_plan_runtime /
             data_tools / agent_tool_specs 的同一套出路，此前只活在代码 hint 里）；
  规则 15 补一句：检索不全类目浏览，中文用途词先换库内数值/型号词；
  规则 19 补一句：其余目录字段可推断登记但须说明依据。

幂等：跑第二遍 changed=0。用法（backend 目录）：
  python -X utf8 scripts/migrate_p5_wave3_left_panel_20260911.py
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

RULE_21 = (
    "21. 引擎返回缺口（gaps）让你转述时：以顾问口吻用一两句自然中文确认第一个缺口，"
    "结合对话上下文措辞、不要模板腔；选项只用 label 文案，系统内部代号不得出现在对客户的话里；"
    "判断只能建立在客户真实表达过的需求和已登记信号上，不得把客户没说过的需求安到客户头上，"
    "不得从无关闲聊里取依据；一次只问一件事；推荐必须逐字取选项 label，没有把握就留空。"
    "客户刚在选项卡上点过选时，先用一句话自然确认收到（如「收到，GPU 就定 10× 曙云C550」），"
    "再转入缺口确认，两段话合成一次回复。"
)
RULE_22 = ("22. 引擎给出「未通过校验」的系统反馈时，照反馈修正参数／换检索路径／"
           "补齐未落地项后重试，不要原样重试。")
RULE_23 = ("23. 库里确实没有客户要的料时，让客户在「改平台／换料／保持原需求」中拍板；"
           "选「保持原需求」用 ask_user 的 waived 选项登记（行保留＋标注「库内无料、客户已知悉」）。"
           "绝不静默丢弃，也不自行编造替代型号。")

RULE_15_OLD = "仍空则不提交、如实说明该查询无结果，禁止断言库里没有。"
RULE_15_NEW = ("仍空则不提交、如实说明该查询无结果，禁止断言库里没有；"
               "检索时不全类目浏览，中文用途词先换成库内数值/型号词（万兆→10G）。")
RULE_19_OLD = "必须先出选项卡让客户确认，才能进配件选型。"
RULE_19_NEW = ("必须先出选项卡让客户确认，才能进配件选型；"
               "其余目录字段可依据客户原话与上下文推断登记并说明依据，不确定的再问。")


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def main() -> int:
    changed = 0
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
            before = len(mr)
            for old, new, tag in ((RULE_15_OLD, RULE_15_NEW, "规则 15 补句"),
                                  (RULE_19_OLD, RULE_19_NEW, "规则 19 补句")):
                if new.split("；")[-1].rstrip("。") in mr:
                    print("[flow:%s] %s 已在" % (fid, tag))
                elif old in mr:
                    mr = mr.replace(old, new, 1)
                    print("[flow:%s] %s 已补" % (fid, tag))
                else:
                    print("[flow:%s] %s 锚点未命中，跳过" % (fid, tag))
            add = [r for r in (RULE_21, RULE_22, RULE_23) if r[:8] not in mr]
            if add:
                mr = (mr.rstrip() + "\n" + "\n".join(add)) if mr.strip() else "\n".join(add)
                print("[flow:%s] manual_rules += %d 条" % (fid, len(add)))
            if mr != str(g.get("manual_rules") or ""):
                g["manual_rules"] = mr
                print("[flow:%s] 左栏 %d -> %d 字" % (fid, before, len(mr)))
                if not DRY:
                    c.execute(sa.text("UPDATE rules.reasoning_flow SET graph=:g WHERE id=:i"),
                              {"g": _dump(g), "i": fid})
                changed += 1
    print("DONE rows_changed=%d dry=%s" % (changed, DRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
