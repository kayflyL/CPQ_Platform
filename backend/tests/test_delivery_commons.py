# -*- coding: utf-8 -*-
"""公共件单测：节点反问原语（留底/匹配/过期）。槽位回填器 slots_backfill 已按
2026-10-30 决定删除（建后零接线，历史见 git），本文件只留仍存活的部分。
全 mock 不触库；pytest 或 `python -X utf8 tests/test_delivery_commons.py` 自跑。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import workflow_ask as wa  # noqa: E402

# ── 节点反问原语 ─────────────────────────────────────────────────────────


def test_ask_answer_happy_path():
    card = wa.ask("run1", "n1", "客户是王瑞吧？归属 Frank？",
                  [{"label": "确认"}, {"label": "取消"}])
    assert card["kind"] == "input_options"
    assert card["options"][0]["label"] == "确认"
    hit = wa.answer("run1", "n1", "确认")
    assert hit["label"] == "确认"
    assert wa.answer("run1", "n1", "确认") is None  # 一次性


def test_ask_scoped_by_run_and_node():
    wa.ask("r1", "n1", "q1", ["a", "b"])
    wa.ask("r2", "n1", "q2", ["a", "b"])
    assert set(wa.pending("r1").keys()) == {"n1"}
    hit = wa.answer("r2", "n1", "a")
    assert hit["label"] == "a"


def test_ask_free_text_answer_passthrough():
    wa.ask("r3", "n2", "客户是谁？", [{"label": "王瑞"}, {"label": "桃红"}])
    hit = wa.answer("r3", "n2", "华为")
    assert hit == {"label": "华为", "value": "华为"}  # 自由回答原样带回，不猜


def test_ask_expiry():
    wa.ask("r4", "n1", "q", ["a"])
    item = wa._pending["r4"]["n1"]
    item["created_at"] -= 3600
    assert wa.answer("r4", "n1", "a") is None
    assert wa.pending("r4") == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
