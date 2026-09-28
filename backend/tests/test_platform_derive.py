# -*- coding: utf-8 -*-
"""平台归置：词典卡知识注入 + 影子校验（知识化注入落地，2026-09-14）。

分层：
- 觹则本体住 CRE（rules.compatibility_rules，DB 唯一来源、无代码种子）；
- 主路径 = 知识注入：requirement_knowledge 把规则渲染成知识块进 brain 系统提示
  （_FillNode.prepare 不再摆桌——摆桌路径已退役）；
- 求值路径降级为影子校验器 + LLM 不可用兜底：catalog_derivations_for_registration
  （空缺槽首命中，逻辑不动），由 shadow_check_platform 包装（对 probe 副本求值，
  AI 是否已填不影响硬命中；永不代填）。
- 推断值不落槽：落槽仍走 fill/ask_user + 前提闸门（unconfirmed_premise_fields）。
"""
from app.services import plan_rule_apply
from app.services.selection_engine import eval_assign_value, registration_rule_context
from app.services.requirement_knowledge import (
    PLATFORM_GROUP, knowledge_for_node, shadow_check_platform)


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
    """兆芯平台归置规则夹具（= DB「平台：CPU 兆芯/KH → Polaris」原样，2026-09-14 导出）。"""
    return {
        "name": "平台：CPU 兆芯/KH → Polaris", "type": "derive", "category": "平台归置",
        "domain": "requirement", "status": "active",
        "body": {
            "when": {"any": [
                {"field": "kp.CPU.spec.text", "op": "contains", "value": "兆芯"},
                {"field": "kp.CPU.spec.text", "op": "contains", "value": "KH"},
                {"field": "kp.CPU.spec.text", "op": "contains", "value": "kh"}]},
            "then": {"action": "derive", "field": "opportunity.platform_type", "value": "Polaris"},
            "desc": "客户点名兆芯（KH 系列）CPU → 整机平台推导为 Polaris；推导值属推断，须经客户确认",
            "evidence": "库内实测：兆芯 KH50000 库存只适配 Polaris 平台"},
    }


# ===== 求值器（影子校验 + LLM 不可用兜底的底座，语义不变） =====

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


# ===== 知识注入（主路径） =====

def test_knowledge_for_agent_fill_renders_platform_block():
    """绑定 agent_fill 的词典组渲染成知识块：标题/规则行（信号→值+依据）/用法行齐全。"""
    text = knowledge_for_node("agent_fill", rules=[_platform_rule()],
                              bindings={"agent_fill": [PLATFORM_GROUP]})
    assert text.startswith("【需求理解知识·平台归置】")
    assert "客户提「兆芯/KH/kh」→ Polaris（依据：库内实测：兆芯 KH50000 库存只适配 Polaris 平台）" in text
    assert "用法：按语义就近归置" in text


def test_knowledge_render_is_byte_stable():
    """确定性渲染：同一规则版本两次渲染逐字节相同（KV cache 前缀友好）。"""
    a = knowledge_for_node("agent_fill", rules=[_platform_rule()],
                           bindings={"agent_fill": [PLATFORM_GROUP]})
    b = knowledge_for_node("agent_fill", rules=[_platform_rule()],
                           bindings={"agent_fill": [PLATFORM_GROUP]})
    assert a == b and a


def test_knowledge_binding_filters_groups():
    """未绑定组/空绑定 → 不注入（选择性靠绑定，不是全量塞给每个节点）。"""
    rules = [_platform_rule()]
    assert knowledge_for_node("agent_fill", rules=rules, bindings={"agent_fill": []}) == ""
    assert knowledge_for_node("model_reason", rules=rules,
                              bindings={"agent_fill": [PLATFORM_GROUP]}) == ""


def test_knowledge_skips_inactive_rules():
    """draft/archived 规则不渲染（只有 active 进知识块）。"""
    r = _platform_rule()
    r["status"] = "draft"
    assert knowledge_for_node("agent_fill", rules=[r],
                              bindings={"agent_fill": [PLATFORM_GROUP]}) == ""


def test_knowledge_degrades_when_rules_unreadable(monkeypatch):
    """规则读取失败 → 空知识块（不带知识继续，回合不阻塞）。"""
    def _boom(domain="requirement"):
        raise RuntimeError("db down")
    monkeypatch.setattr(plan_rule_apply, "load_active_rules", _boom)
    assert knowledge_for_node("agent_fill",
                              bindings={"agent_fill": [PLATFORM_GROUP]}) == ""


# ===== 影子校验（词典卡专属；永不代填） =====

def test_shadow_hard_hit_reports_rule_value():
    """兆芯信号硬命中 → {slot, rule_value}；比对（标推荐/告警）由调用方做。"""
    got = shadow_check_platform(_zhaoxin_ext(), rules=[_platform_rule()])
    assert got == {"slot": "platform_type", "rule_value": "Polaris"}


def test_shadow_hit_independent_of_ai_value():
    """probe 语义：AI 已填 platform_type=Orion 不影响硬命中计算（规则说该是什么）。"""
    got = shadow_check_platform(_zhaoxin_ext(platform="Orion"), rules=[_platform_rule()])
    assert got == {"slot": "platform_type", "rule_value": "Polaris"}


def test_shadow_no_hit_returns_none():
    """无 CPU 信号（AMD）→ None（不干预，AI 外推照常走推断确认）。"""
    amd = _zhaoxin_ext()
    amd["kp_rows"][0]["request_spec"] = "EPYC 9654"
    assert shadow_check_platform(amd, rules=[_platform_rule()]) is None


def test_shadow_degrades_when_rules_unreadable(monkeypatch):
    def _boom(domain="requirement"):
        raise RuntimeError("db down")
    monkeypatch.setattr(plan_rule_apply, "load_active_rules", _boom)
    assert shadow_check_platform(_zhaoxin_ext()) is None
