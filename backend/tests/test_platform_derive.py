# -*- coding: utf-8 -*-
"""S4 平台推导：CRE 选型规则在登记阶段推导空缺目录槽（CPU 兆芯 → 平台 Polaris）。

分层：
- 规则本体住 CRE（rules.compatibility_rules，DEFAULT_RULES seed「平台：CPU 兆芯/KH → Polaris」）；
- 登记表侧只接线：registration_rule_context（登记表→求值 ctx）+
  plan_rule_apply.catalog_derivations_for_registration（空缺槽首命中）+
  _FillNode.prepare 摆桌（事实行进【步骤准备】，指令住在左栏规则 13/19）。
- 推断值不落槽：落槽仍走 fill/ask_user + 前提闸门（unconfirmed_premise_fields）。
"""
import asyncio
from unittest.mock import patch

from app.services import plan_rule_apply
from app.services.selection_engine import eval_assign_value, registration_rule_context


def _zhaoxin_ext(platform: str = "") -> dict:
    return {
        "server_type": "通用计算服务器",
        "platform_type": platform,
        "kp_rows": [
            {"part_category": "CPU", "request_spec": "兆芯50000（2.2GHz/96C）", "qty": 2},
            {"part_category": "Memory", "request_spec": "DDR5 64G", "qty": 12},
        ],
    }


def _platform_rule() -> dict:
    from app.repository.compatibility_rule_repo import DEFAULT_RULES
    return next(r for r in DEFAULT_RULES if "兆芯" in r["name"])


def test_default_rules_seed_zhaoxin_platform_rule_active():
    """规则在 DEFAULT_RULES 且 active：startup seed_missing_defaults 会自动流库。"""
    rule = _platform_rule()
    assert rule["status"] == "active"
    assert rule["body"]["then"] == {
        "action": "derive", "field": "opportunity.platform_type", "value": "Polaris"}


def test_registration_context_exposes_cpu_text_and_qty():
    ctx = registration_rule_context(_zhaoxin_ext())
    cpu = ctx["kp"]["CPU"]
    assert cpu["qty"] == 2
    assert "兆芯" in (cpu["spec"].get("text") or "")
    assert ctx["config"].get("server_type") == "通用计算服务器"


def test_zhaoxin_cpu_row_derives_polaris():
    """兆芯 CPU 行命中规则 → 平台推导 Polaris；无 CPU 信号（AMD）→ 不命中。"""
    ctx = registration_rule_context(_zhaoxin_ext())
    assert eval_assign_value([_platform_rule()], ctx, "opportunity.platform_type") == "Polaris"

    amd = _zhaoxin_ext()
    amd["kp_rows"][0]["request_spec"] = "EPYC 9654"
    assert eval_assign_value([_platform_rule()], registration_rule_context(amd),
                             "opportunity.platform_type") is None


def test_catalog_derivations_only_for_empty_slot():
    """只推导空缺槽：已登记平台以登记表为准；无规则 → 空（降级不阻塞）。"""
    rules = [_platform_rule()]
    assert plan_rule_apply.catalog_derivations_for_registration(_zhaoxin_ext(), rules) \
        == [("platform_type", "Polaris")]
    assert plan_rule_apply.catalog_derivations_for_registration(
        _zhaoxin_ext(platform="Polaris"), rules) == []
    assert plan_rule_apply.catalog_derivations_for_registration(_zhaoxin_ext(), rules=[]) == []


def test_fill_prepare_hint_carries_derivation_fact():
    """agent_fill 步骤准备摆桌：推导值以事实行出现（含槽位名与「推断值」标注）。"""
    from app.services.skill_node_plugins import _FillNode
    with patch.object(plan_rule_apply, "load_active_rules", return_value=[_platform_rule()]):
        res = asyncio.run(_FillNode().prepare({"ext": _zhaoxin_ext()}, {}))
    assert res.get("ok") is True
    assert "(platform_type)=Polaris" in res["hint"]
    assert "推断值" in res["hint"]

    with patch.object(plan_rule_apply, "load_active_rules", return_value=[_platform_rule()]):
        res2 = asyncio.run(_FillNode().prepare({"ext": _zhaoxin_ext(platform="Orion")}, {}))
    assert "platform_type=" not in res2["hint"]


def test_fill_prepare_degrades_when_rules_unreadable():
    """规则读取失败 → 步骤照常就绪（不带推导值），登记回合不被规则层阻塞。"""
    from app.services.skill_node_plugins import _FillNode

    def _boom():
        raise RuntimeError("db down")

    with patch.object(plan_rule_apply, "load_active_rules", _boom):
        res = asyncio.run(_FillNode().prepare({"ext": _zhaoxin_ext()}, {}))
    assert res.get("ok") is True
    assert "Polaris" not in res["hint"]
