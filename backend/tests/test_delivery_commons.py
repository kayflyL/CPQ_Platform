# -*- coding: utf-8 -*-
"""公共件单测：槽位回填器（确定性回填/缺口/兜底）+ 节点反问原语（留底/匹配/过期）。
全 mock 不触库；pytest 或 `python -X utf8 tests/test_delivery_commons.py` 自跑。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import slots_backfill as sb  # noqa: E402
from app.services import workflow_ask as wa  # noqa: E402

SPEC = [
    {"key": "server_model", "label": "机型"},
    {"key": "chassis_form", "label": "机箱形态"},
    {"key": "purchase_qty", "label": "数量", "default_value": 1},
    {"key": "warranty_years", "label": "维保年限"},
]


# ── 槽位回填器 ───────────────────────────────────────────────────────────


def test_backfill_fills_and_reports_missing():
    out = sb.backfill({"server_model": "ZS22EV1-Z", "chassis_form": "2U"},
                      source="表格解析", spec=SPEC)
    assert out["ok"] is True
    assert out["filled"]["server_model"] == {"value": "ZS22EV1-Z", "source": "表格解析"}
    # 数量走契约默认兜底
    assert out["filled"]["purchase_qty"]["value"] == 1
    assert out["filled"]["purchase_qty"]["source"] == "默认兜底"
    assert out["missing"] == ["warranty_years"]
    assert out["draft_slots"]["server_model"] == "ZS22EV1-Z"
    assert out["draft_slots"]["purchase_qty"] == 1


def test_backfill_ignores_keys_outside_contract():
    out = sb.backfill({"server_model": "X", "customer_mood": "好"}, spec=SPEC)
    assert out["ignored"] == {"customer_mood": "好"}
    assert "customer_mood" not in out["draft_slots"]


def test_backfill_question_for_first_gap():
    out = sb.backfill({"server_model": "X"}, spec=SPEC)
    q = sb.question_for(out["missing"])
    assert q and q["key"] == "chassis_form"
    assert sb.question_for([]) is None


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
