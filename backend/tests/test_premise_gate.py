# -*- coding: utf-8 -*-
"""B（目录前提闸门）：决定「库里有没有料」的目录字段必须经客户拍板才能进配件选配。

背景（2026-09 实测）：配件库的料按平台/系列过滤适用性（part_selector._SeriesScopedRepo）。
平台是 AI 推断值、客户从没说过时，下游每一行都会「无料可锁」，实测 10 轮不收敛。

口径（不写词表）：
  * 「哪些字段是前提」= 登记表字段契约里 catalog_dimension == series 的字段（字段配置可改）；
  * 「算不算客户确认过」= ext.confirmed_slots（点选确认卡 / 打字精确命中同一选项）——
    值被改写即失效，与 2026-09-06 的既定口径同一把权威源；
  * 大脑申报「这是客户原话」走 fill_requirement(customer_stated=[...])，落同一把权威源。
"""

import os
import sys
from app.services import skill_tool_context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _premise_keys() -> set:
    from app.services.slot_contract import slot_spec
    return {str(s.get("key") or "") for s in slot_spec()
            if str(s.get("catalog_dimension") or "") == "series"}


def test_premise_fields_come_from_the_field_contract_not_a_wordlist():
    """前提字段集 = 字段契约里 series 维度的字段；契约改了，闸门跟着改。"""
    keys = _premise_keys()
    assert keys, "登记表契约里应当有 series 维度的目录字段"
    assert "platform_type" in keys
    assert "server_type" not in keys, "非前提字段不该被闸门拦住"


def test_inferred_premise_is_reported_unconfirmed():
    """AI 推断填上的平台（客户没说过）→ 报未确认前提（含字段 key/标签/当前值）。"""
    from app.services.slot_contract import unconfirmed_premise_fields
    key = sorted(_premise_keys())[0]
    gaps = unconfirmed_premise_fields({"server_type": "通用计算服务器", key: "Polaris"})
    assert [g["key"] for g in gaps] == [key]
    assert gaps[0]["value"] == "Polaris" and gaps[0]["label"]


def test_customer_clicked_confirmation_clears_the_gate():
    """客户点选确认卡 → confirmed_slots 有记录 → 不再是缺口。"""
    from app.services.slot_contract import unconfirmed_premise_fields
    key = sorted(_premise_keys())[0]
    ext = {key: "Polaris", "confirmed_slots": {key: "Polaris"}}
    assert unconfirmed_premise_fields(ext) == []


def test_value_changed_after_confirmation_invalidates_it():
    """确认之后值被改写 → 原确认失效（旧确认不能给新值背书）。"""
    from app.services.slot_contract import unconfirmed_premise_fields
    key = sorted(_premise_keys())[0]
    ext = {key: "Orion", "confirmed_slots": {key: "Polaris"}}
    assert [g["key"] for g in unconfirmed_premise_fields(ext)] == [key]


def test_empty_premise_is_not_a_premise_gap():
    """字段还没填 → 归「缺字段」闸门管，不由前提闸门重复报。"""
    from app.services.slot_contract import unconfirmed_premise_fields
    assert unconfirmed_premise_fields({"server_type": "通用计算服务器"}) == []


def test_field_confirmation_option_binds_a_real_signal():
    """确认卡选项带 slot+value → 点击信号就是「写该字段 = 规范值」（value 不是给客户看的文案）。"""
    from app.services.skill_plan_runtime import ask_option_signal
    sig = ask_option_signal("", {"label": "Polaris（兆芯平台）", "value": "Polaris", "slot": "platform_type"})
    assert sig == {"platform_type": "Polaris"}


def test_field_confirmation_option_without_value_does_not_write_a_field():
    """只给 label 没给 value → 不绑字段（绝不让文案落进目录字段），答案留给大脑消化。"""
    from app.services.skill_plan_runtime import ask_option_signal
    assert ask_option_signal("", {"label": "Polaris（兆芯平台）"}, "platform_type") == {}


def test_clicking_a_field_confirmation_writes_the_field_and_the_mark():
    """点选确认卡的落值通路：写字段（登记通道）+ 记 confirmed_slots（求证侧留痕）。"""
    from app.services.skill_signals import _apply_registration_signal
    ext: dict = {"server_type": "通用计算服务器"}
    assert _apply_registration_signal(ext, {"platform_type": "Polaris"}) is True
    assert ext["platform_type"] == "Polaris"
    ext.setdefault("confirmed_slots", {})["platform_type"] = "Polaris"
    from app.services.slot_contract import unconfirmed_premise_fields
    assert unconfirmed_premise_fields(ext) == []


def test_registration_signal_ignores_non_registration_keys():
    """信号里的部件槽/未知键不归这条通道管（各通道边界清晰，不互相吞）。"""
    from app.services.skill_signals import _apply_registration_signal
    ext: dict = {}
    assert _apply_registration_signal(ext, {"cpu": [{"qty": 2}]}) is False
    assert not ext


def test_brain_can_declare_the_customer_said_it():
    """大脑申报客户原话（customer_stated）→ 落同一把权威源，不必再问客户一遍。"""
    from app.services.skill_tools_fill import tool_fill_requirement
    from app.services.skill_plan_runtime import validate_step_end
    from app.services.slot_contract import unconfirmed_premise_fields
    from app.services import skill_chat
    from app.services import skill_signals
    from app.services import skill_tools_fill
    key = sorted(_premise_keys())[0]
    ext: dict = {}
    skill_tool_context.TOOL_CTX.set({"task_active": True, "ext": ext, "save": None})
    res = tool_fill_requirement({"server_type": "通用计算服务器", key: "Polaris",
                                 "purchase_qty": 1, "customer_stated": [key]})
    assert res.get("ok") is True and res.get("customer_stated") == [key]
    assert ext.get("confirmed_slots", {}).get(key) == "Polaris"
    assert unconfirmed_premise_fields(ext) == []

    import asyncio
    v = asyncio.run(validate_step_end({"ext": ext, "flow_configs": {}}, "agent_fill"))
    assert v.get("ok") is True, v


def test_customer_stated_only_accepts_catalog_fields():
    """申报只对目录字段生效：瞎报别的键（如 free 字段/未知键）不写确认记录。"""
    from app.services.skill_tools_fill import tool_fill_requirement
    from app.services import skill_chat
    ext: dict = {}
    skill_tool_context.TOOL_CTX.set({"task_active": True, "ext": ext, "save": None})
    res = tool_fill_requirement({"server_type": "通用计算服务器", "purchase_qty": 1,
                                 "customer_stated": ["purchase_qty", "not_a_field"]})
    assert res.get("customer_stated") == []
    assert "purchase_qty" not in (ext.get("confirmed_slots") or {})


def test_fill_tool_contract_exposes_customer_stated_data_drivenly():
    """工具契约跟着字段配置走：目录字段都在 customer_stated 的枚举里（不写死字段名）。"""
    from app.services.skill_tools_fill import fill_tool_parameters
    from app.services.slot_contract import catalog_field_keys
    props = fill_tool_parameters()["properties"]
    enum = set(((props.get("customer_stated") or {}).get("items") or {}).get("enum") or [])
    assert enum == catalog_field_keys() & set(props)
    assert enum, "customer_stated 的枚举必须由字段契约生成" 
