# -*- coding: utf-8 -*-
"""机型选型节点完成产物回归：节点「查看完整」必须是目标层 L6 机箱表，而不是裸 JSON。

2026-09-09：_node_done_payload 对 model_reason 由 kind=model_choice（裸 JSON）改为
kind=l6_chassis（chosen/reason + BOM 模板求值出的 rows），对齐目标层抽屉预览 /l6-preview。
"""
from app.services import skill_step_runtime
from unittest.mock import patch

from app.services.skill_step_runtime import _node_done_payload
from app.services.skill_node_artifacts import locked_l6_rows as _locked_l6_rows


def _drawer() -> dict:
    """真实抽屉配置：产物槽由抽屉声明（代码里没有节点→产物兜底表）。"""
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    repo = ReasoningFlowRepository()
    try:
        return (repo.ensure_skill_flow("requirement_analysis", name="需求分析")
                or {}).get("node_configs") or {}
    finally:
        repo.close()


def test_model_reason_done_payload_emits_l6_chassis_table():
    """机型选型完成：产物 kind=l6_chassis，data 含 chosen/reason/rows（目标层表格）。"""
    locked = {"id": 7, "bom_template_id": 3, "name": "ES220 V3"}
    engine = {
        "_locked_baseline": locked,
        "lock_reason": "目录唯一命中",
        "baselines_pool": [{"name": "ES220 V3"}],
        "ext": {"server_model": "ES220 V3"},
        "flow_configs": _drawer(),
    }
    rows = [{"catalogue": "Front backplane", "description": "12*3.5 SATA/SAS", "qty": 1},
            {"catalogue": "IO1", "description": "1*X8 FHFL", "qty": 1}]
    with patch("app.services.bom_template_eval.eval_l6_rows", return_value=rows), \
         patch("app.repository.bom_case_repo._l6_rows_from_base_config", return_value=rows):
        payload = _node_done_payload(engine, "model_reason", "机型选型", "已锁定")
    art = payload["artifact"]
    assert art["kind"] == "l6_chassis"
    assert art["data"]["chosen"] == "ES220 V3"
    assert art["data"]["reason"] == "目录唯一命中"
    assert art["data"]["rows"] == rows
    assert payload["output"]["l6_rows_count"] == 2


def test_locked_l6_rows_falls_back_to_base_config_when_template_missing():
    """锁定机型无 BOM 模板 id：跳过模板求值，回退基准配置行。"""
    locked = {"id": 9, "bom_template_id": None, "name": "X"}
    rows = [{"catalogue": "IO1", "description": "1*X8 FHFL", "qty": 1}]
    with patch("app.repository.bom_case_repo._l6_rows_from_base_config", return_value=rows):
        assert _locked_l6_rows(locked) == rows


def test_locked_l6_rows_returns_empty_without_base_config_id():
    """无 base_config_id（未锁定）时不产出 L6 行。"""
    assert _locked_l6_rows({"bom_template_id": 1}) == []
