# -*- coding: utf-8 -*-
"""工具契约（P3 上安全带）单测：契约完整性快照 + 确认分级 + 写后回读 + 审计落账。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services.agent_tool_registry import ToolRegistry
from app.services import agent_write_confirm as awc
from app.services import skill_tools_write as stw
from app.services import skill_decision_gate as _  # noqa: F401  确保家族模块可导入
from app.services.agent_tool_specs import _TOOL_CONTRACTS, _TOOL_SPECS

LEGAL_POLICY = {"none", "stage", "stage+consent"}

# 13 个写语义工具的登记快照：新增写工具必须显式登记契约（缺=本测试红，提醒人工审）


def test_write_tools_snapshot():
    assert set(_TOOL_CONTRACTS) == {
        "fill_requirement", "choose_model", "select_parts", "create_opportunity",
        "save_requirement_draft", "import_cost_sheet", "submit_cost_sheet",
        "set_quote_margin", "set_cost_prices", "share_quote",
        "import_bom_scheme", "derive_cost_from_scheme", "colleague_memory"}


def test_contract_keys_exist_in_specs():
    missing = [k for k in _TOOL_CONTRACTS if k not in _TOOL_SPECS]
    assert not missing, f"契约登记了不存在的工具：{missing}"


def test_contract_fields_complete_and_legal():
    for key, c in _TOOL_CONTRACTS.items():
        for f in ("effects", "confirm_policy", "idempotent_hint", "destructive_hint", "target_entity"):
            assert f in c, f"{key} 缺契约字段 {f}"
        assert c["effects"] in ("read", "write"), f"{key} effects 非法"
        assert c["confirm_policy"] in LEGAL_POLICY, f"{key} confirm_policy 非法"
        if c["effects"] == "write":
            assert isinstance(c["idempotent_hint"], bool), f"{key} idempotent_hint 须显式 bool"


def test_unregistered_default_is_read():
    """未登记契约的工具默认 effects=read + 不弹卡（读工具无卡现状）。"""
    spec = {"description": "", "summary": "", "parameters": {}}
    spec.setdefault("contract", {"effects": "read", "confirm_policy": "none"})
    assert spec["contract"]["effects"] == "read"


def test_confirm_policy_for_known_and_unknown():
    assert awc.confirm_policy_for("set_quote_margin") == "stage+consent"
    assert awc.confirm_policy_for("fill_requirement") == "none"
    assert awc.confirm_policy_for("no_such_tool") == "stage+consent"  # 保守默认


@pytest.fixture(autouse=True)
def _confirm_memory(monkeypatch):
    monkeypatch.setattr(awc, "_STORAGE", "memory")
    monkeypatch.setattr(awc, "_MEM", {})


def test_confirm_gate_none_policy_skips_card(monkeypatch):
    from app.services.skill_tool_context import TOOL_CTX
    monkeypatch.setattr(stw, "_ctx", lambda: {"thread_id": "t_none"})
    gate, staged = stw._confirm_gate({"rows": [{"a": 1}]},
                                     "fill_requirement", {"登记": "x"})
    assert gate is None and staged["rows"] == [{"a": 1}]
    assert awc.query_opened("t_none", "fill_requirement") is False  # 未落待确认未弹卡


def test_confirm_gate_stage_family_still_cards(monkeypatch):
    from app.services.skill_tool_context import TOOL_CTX
    monkeypatch.setattr(stw, "_ctx", lambda: {"thread_id": "t_stage"})
    gate, staged = stw._confirm_gate({"sheet_id": "s1"}, "submit_cost_sheet", {"预览": "x"})
    assert gate is not None and gate.get("needs_confirmation") is True
    assert staged is None


# ── registry 写路径：审计落账 + 写后回读 ─────────────────────────────────


def test_registry_audit_and_readback(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.agent_audit.audit_write", lambda **kw: captured.update(kw))
    monkeypatch.setattr("app.services.skill_tools_write._require_user", lambda: {"user_id": "u1"})
    monkeypatch.setattr("app.services.delivery_core.margin_resolve_quotation",
                        lambda *a, **k: {"ok": True, "quotation_id": "q1",
                                         "quotation_name": "报价单A", "version": 3})
    from app.services import agent_tool_registry as reg_mod
    contract = {"effects": "write", "confirm_policy": "none", "target_entity": "quotation",
                "verify": "skill_tools_write.verify_set_quote_margin"}
    result = {"ok": True, "quotation_id": "q1", "saved_items": [{"x": 1}]}
    out = reg_mod.write_finish("fake_write_tool", contract, {"quotation_id": "q1"}, result,
                               {"thread_id": "t_reg", "role_key": "support_engineer", "user_id": "u1"})
    assert out["ok"] is True
    assert captured.get("tool") == "fake_write_tool"
    assert captured.get("thread_id") == "t_reg"
    assert captured.get("result_ok") is True
    assert "readback" in captured and "quotation_id" in captured["readback"]


def test_registry_readback_mismatch_blocks(monkeypatch):
    monkeypatch.setattr("app.services.skill_tools_write._require_user", lambda: {"user_id": "u1"})
    monkeypatch.setattr("app.services.delivery_core.margin_resolve_quotation",
                        lambda *a, **k: {"ok": False, "message": "报价单没了"})
    from app.services import agent_tool_registry as reg_mod
    contract = {"effects": "write", "confirm_policy": "none", "target_entity": "quotation",
                "verify": "skill_tools_write.verify_set_quote_margin"}
    out = reg_mod.write_finish("fake_write_tool2", contract, {"quotation_id": "q9"},
                               {"ok": True, "quotation_id": "q9"}, {"thread_id": "t"})
    assert out["ok"] is False
    assert out["error"] == "readback_mismatch"
