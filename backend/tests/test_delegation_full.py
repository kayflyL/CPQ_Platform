# -*- coding: utf-8 -*-
"""整单委托（delegation=full）：推断豁免逐项求证，确认收敛到整体落定卡一次完成——2026-09-13。

客户明示全权委托（用户定调：不然系统一点智能性都没有了）时：
fill_requirement 申报 → premise 闸门放行（大脑代定前提字段）→
整体卡点击连带确认目录字段（机型除外，机型走 choose_model 确认）。
"""
from app.services import skill_tool_context


def _ext_with_catalog(confirmed=None):
    return {"platform_type": "Orion", "server_type": "通用计算服务器",
            "confirmed_slots": dict(confirmed or {})}


def test_premise_gate_suppressed_under_blanket_delegation():
    from app.services.slot_contract import unconfirmed_premise_fields
    ext = _ext_with_catalog()
    assert unconfirmed_premise_fields(ext), "非委托基线：未确认前提应当被报出"
    ext["delegation"] = "full"
    assert unconfirmed_premise_fields(ext) == []


def test_fill_tool_delegation_declaration_persists():
    from app.services.skill_tools_fill import tool_fill_requirement
    ext = {}
    skill_tool_context.TOOL_CTX.set({"task_active": True, "ext": ext, "save": None})
    out = tool_fill_requirement({"server_type": "通用计算服务器",
                                 "platform_type": "Orion", "delegation": "full"})
    assert out.get("ok"), out
    assert ext.get("delegation") == "full"
    assert out.get("delegation") == "full"
    assert "delegation" not in (out.get("unrecognized_keys") or [])


def test_fill_tool_without_delegation_declaration_stays_off():
    from app.services.skill_tools_fill import tool_fill_requirement
    ext = {}
    skill_tool_context.TOOL_CTX.set({"task_active": True, "ext": ext, "save": None})
    out = tool_fill_requirement({"server_type": "通用计算服务器"})
    assert out.get("ok"), out
    assert "delegation" not in ext


def test_bulk_click_confirms_catalog_fields_except_models():
    from app.services.slot_contract import confirm_registration_on_bulk_click
    ext = _ext_with_catalog()
    ext["delegation"] = "full"
    ext["server_model"] = "ES220 V3"
    got = confirm_registration_on_bulk_click(ext)
    conf = ext["confirmed_slots"]
    assert conf.get("platform_type") == "Orion"
    assert conf.get("server_type") == "通用计算服务器"
    assert "server_model" not in conf
    assert {"platform_type", "server_type"} <= set(got)
    # 幂等：再点一次不重复记
    assert confirm_registration_on_bulk_click(ext) == []
