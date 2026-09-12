# -*- coding: utf-8 -*-
"""左栏任务规则 15 改口径（2026-09-12，一次性；可重复执行）。

配件落地机制已从「检索台账」改成「直连库、按料号名核对」（A1/A2），左栏第 15 条却仍在
描述台账流程（先 query_parts 检索 → 再从检索结果 select_parts 提交）。说明与机制不一致，
大脑照旧文办事 = 必然返工。本脚本只改第 15 条，其余各条原样保留。

新口径：落行凭料号名；唯一命中才落行、价格取库内最新值；同名料号多命中回全部候选让 AI
确认；零命中回白盒消息；禁止断言库里没有；不全类目浏览。

幂等：跑第二遍 changed=0。用法（backend 目录）：
  python -X utf8 scripts/migrate_left_panel_rule15_20260912.py
  加 CPQ_DRY=1 只打印不落库。
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlalchemy as sa

from app.models.base import Rules_SessionLocal

DRY = os.environ.get("CPQ_DRY") == "1"
SKILL_KEY = "requirement_analysis"

RULE_15 = (
    "15.【配件步】落行按料号名：select_parts 的 picks 填 name（料号名，库里没有业务 part_id），"
    "引擎按「类目+料号名」（忽略大小写/空格差异）回库精确核对——唯一命中才落行、价格取库里最新值；"
    "库内同名料号多命中时未落料、把全部同名行回候选，从候选里确认后重新提交；零命中回白盒消息，"
    "换关键词或换检索路径再试，禁止断言库里没有。料号名取自库内返回原文（query_parts 的 keywords "
    "用库内拉丁型号/厂商词，规格收窄用 required_specs 如 Type=DDR5、Capacity=6TB），不凭记忆编造；"
    "检索时不全类目浏览，中文用途词先换成库内数值/型号词（万兆→10G）。组合需求给 qty，"
    "近替代带 substitute=true 并写明原需求→替代。"
)
# 新文案必须自带的锚点（与 tests/test_constitution.py MOVED_RULES 一致）
REQUIRED = ["禁止断言库里没有", "不全类目浏览", "同名料号"]
RULE_PREFIX = "15."


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def swap_rule15(mr: str) -> tuple:
    """把以「15.」开头的那一整行换成新口径；已换过则原样返回。"""
    lines = mr.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(RULE_PREFIX):
            if line.strip() == RULE_15:
                return mr, False
            lines[i] = RULE_15
            return "\n".join(lines), True
    lines.append(RULE_15)
    return "\n".join(lines), True


def main() -> int:
    changed = 0
    s = Rules_SessionLocal()
    try:
        fid = s.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow WHERE skill_key=:s AND is_active IS TRUE"
            " ORDER BY id DESC LIMIT 1"), {"s": SKILL_KEY}).scalar()
        if fid is None:
            print("[flow] 没有生效流程，跳过")
            return 1
        raw = s.execute(sa.text("SELECT graph FROM rules.reasoning_flow WHERE id=:i"),
                        {"i": fid}).scalar()
        g = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        mr = str(g.get("manual_rules") or "")
        new_mr, swapped = swap_rule15(mr)
        missing = [a for a in REQUIRED if a not in new_mr]
        if missing:
            print("[abort] 新文案缺锚点 %s，未落库" % missing)
            return 1
        if not swapped:
            print("[flow:%s] 任务规则 15 已是新口径" % fid)
        else:
            print("[flow:%s] 任务规则 15 改口径（%d -> %d 行，%d -> %d 字）"
                  % (fid, len(mr.split("\n")), len(new_mr.split("\n")), len(mr), len(new_mr)))
            g["manual_rules"] = new_mr
            if not DRY:
                s.execute(sa.text(
                    "UPDATE rules.reasoning_flow SET graph=:g, updated_by='left-panel-rule15'"
                    " WHERE id=:i"), {"g": _dump(g), "i": fid})
                s.commit()
            changed += 1
    finally:
        s.close()
    print("DONE rows_changed=%d dry=%s" % (changed, DRY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
