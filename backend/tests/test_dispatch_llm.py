# -*- coding: utf-8 -*-
"""智能转接（LLM 判官）测试：mock chat_json，验证名册判断契约与安全降级。"""
import asyncio

import pytest

from app.services import ai_colleague_service as svc

TEST_CFG = {
    "dispatch_enabled": True,
    "colleagues": [
        {"role_key": "assistant", "name": "方案助手", "enabled": True, "dispatchable": False,
         "system_prompt": "你是 CPQ 平台的方案助手，负责理解用户意图并分派给合适的 AI 同事。", "skills": []},
        {"role_key": "cost_analyst", "name": "成本核算", "enabled": True, "dispatchable": True,
         "system_prompt": "负责整机成本测算、成本结构与利润分析", "skills": ["cost"]},
        {"role_key": "support_engineer", "name": "技术支持工程师", "enabled": True, "dispatchable": True,
         "opening_message": "需求分析与服务器选型", "skills": ["requirement_analysis"]},
        {"role_key": "sleepy", "name": "停用同事", "enabled": False, "dispatchable": True},
    ],
    # 判官用总助自己的提示词（Manage Teams · 员工），不再有 behavior.charter 桶
}


def _patch_cfg(monkeypatch, cfg=None):
    monkeypatch.setattr(svc, "_load_config", lambda: dict(cfg or TEST_CFG))


def _install(monkeypatch, result=None, error=None, calls=None):
    async def fake_chat_json(messages, **kwargs):
        if calls is not None:
            calls.append(messages)
        if error:
            raise error
        return result
    import app.services.llm_client as llm
    monkeypatch.setattr(llm, "chat_json", fake_chat_json)


def test_disabled_dispatch_skips_llm(monkeypatch):
    cfg = dict(TEST_CFG)
    cfg["dispatch_enabled"] = False
    _patch_cfg(monkeypatch, cfg)
    calls = []
    _install(monkeypatch, result={"colleague_role_key": "cost_analyst", "reason": "x"}, calls=calls)
    assert asyncio.run(svc.resolve_assistant_message_target_async("算下成本")) is None
    assert calls == []  # 关闭时不应发起 LLM 调用


def test_llm_picks_cost_analyst(monkeypatch):
    _patch_cfg(monkeypatch)
    calls = []
    _install(monkeypatch, result={"colleague_role_key": "cost_analyst", "reason": "成本问题"}, calls=calls)
    got = asyncio.run(svc.resolve_assistant_message_target_async("帮我算一下这台机器的成本明细"))
    assert got is not None and got["role_key"] == "cost_analyst"
    assert got["_dispatch_reason"] == "成本问题"
    # 名册进入 prompt：包含可转派同事职责，不含停用/不可转派同事
    user_text = calls[0][1]["content"]
    assert "成本核算" in user_text and "整机成本测算" in user_text
    assert "停用同事" not in user_text and "方案助手" not in user_text


def test_invalid_role_returns_none(monkeypatch):
    _patch_cfg(monkeypatch)
    _install(monkeypatch, result={"colleague_role_key": "nonexistent", "reason": "x"})
    assert asyncio.run(svc.resolve_assistant_message_target_async("任何消息")) is None


def test_llm_failure_degrades_to_none(monkeypatch):
    _patch_cfg(monkeypatch)
    _install(monkeypatch, error=RuntimeError("timeout"))
    assert asyncio.run(svc.resolve_assistant_message_target_async("任何消息")) is None


def test_dispatchable_false_excluded(monkeypatch):
    _patch_cfg(monkeypatch, {"dispatch_enabled": True, "colleagues": [
        {"role_key": "a", "name": "甲", "enabled": True, "dispatchable": False},
    ]})
    calls = []
    _install(monkeypatch, result={"colleague_role_key": "a", "reason": "x"}, calls=calls)
    assert asyncio.run(svc.resolve_assistant_message_target_async("x")) is None
    assert calls == []  # 名册为空则不起判


def test_explicit_role_key_resolution(monkeypatch):
    _patch_cfg(monkeypatch)
    got = svc.resolve_dispatch_target(role_key="cost_analyst")
    assert got is not None and got["role_key"] == "cost_analyst"
    assert svc.resolve_dispatch_target(role_key="sleepy") is None  # 停用不可选


def test_team_lead_role_key(monkeypatch):
    # 默认 leader = 方案助手（assistant）；画布 team_graph 可改
    _patch_cfg(monkeypatch, {"colleagues": []})
    assert svc.get_team_lead_role_key() == "assistant"
    _patch_cfg(monkeypatch, {"layout": {"team_graph": {"lead_role_key": "cost_analyst"}}, "colleagues": []})
    assert svc.get_team_lead_role_key() == "cost_analyst"


def test_find_mentioned_colleague(monkeypatch):
    _patch_cfg(monkeypatch)
    assert svc.find_mentioned_colleague("这个问题@成本核算 更清楚").get("role_key") == "cost_analyst"
    assert svc.find_mentioned_colleague("@cost_analyst 帮我算").get("role_key") == "cost_analyst"
    assert svc.find_mentioned_colleague("帮我@成本核算一下") .get("role_key") == "cost_analyst"
    assert svc.find_mentioned_colleague("没有点名 @不存在的同事") is None
    assert svc.find_mentioned_colleague("纯文本没有 @ 符号") is None
    assert svc.find_mentioned_colleague("") is None
    # 停用/不可转派不可被点名
    assert svc.find_mentioned_colleague("@停用同事 你好") is None
    # 邮箱类文本不误判（@后跟在册名以外内容）
    assert svc.find_mentioned_colleague("发到 mail@a.com") is None


def test_handle_skill_chat_turn_smoke(monkeypatch):
    """对话脑入口冒烟：曾因 role_key 先用后赋值在第一行就 UnboundLocalError（全链路无覆盖未被发现）。"""
    import asyncio
    import app.services.skill_chat as sc

    async def fake_loop(*args, **kwargs):
        return {"ok": True, "answer": "好的，收到"}

    monkeypatch.setattr(sc, "run_stream_chat_loop", fake_loop)
    monkeypatch.setattr(sc, "_load_mem", lambda tid, rk="assistant": {})
    monkeypatch.setattr(sc, "_save_mem", lambda tid, rk, mem: None)

    out = asyncio.run(sc.handle_skill_chat_turn(
        thread_id="t-smoke", user_text="你好",
        colleague={"role_key": "assistant", "price_access": True},
        chat_system_prompt="x", history=[],
    ))
    assert out["kind"] == "chat"
    assert out["reply"] == "好的，收到"


# ── 2026-08-30 定调：转接只在群里（绑定会话含方案助手永不转接）─────────────

def test_bound_session_never_dispatches(monkeypatch):
    """绑定 1:1 会话（含方案助手自己）锁定身份：判官一次都不该被调用。"""
    _patch_cfg(monkeypatch)
    calls = []
    _install(monkeypatch, result={"colleague_role_key": "support_engineer", "reason": "x"}, calls=calls)
    for bound in ("assistant", "cost_analyst"):
        colleague, dispatch = asyncio.run(svc.resolve_chat_target(bound, "我想要一台服务器"))
        assert colleague is not None and colleague["role_key"] == bound
        assert dispatch is None
    assert calls == []


def test_unbound_group_dispatches_via_judge(monkeypatch):
    """未绑定线程=团队群：@点名确定性路由优先；无 @ 时判官决定并要求落转接标记。"""
    _patch_cfg(monkeypatch)
    calls = []
    _install(monkeypatch, result={"colleague_role_key": "cost_analyst", "reason": "成本"}, calls=calls)
    colleague, dispatch = asyncio.run(svc.resolve_chat_target(None, "帮我算下成本"))
    assert colleague["role_key"] == "cost_analyst"
    assert dispatch is not None and dispatch["role_key"] == "cost_analyst"
    assert calls, "群内无点名应走判官"
    # @点名不走判官
    calls.clear()
    colleague, dispatch = asyncio.run(svc.resolve_chat_target(None, "@成本核算 看看"))
    assert colleague["role_key"] == "cost_analyst" and dispatch is None
    assert calls == []


def test_unbound_judge_none_falls_back_to_leader(monkeypatch):
    _patch_cfg(monkeypatch)
    _install(monkeypatch, error=RuntimeError("down"))
    colleague, dispatch = asyncio.run(svc.resolve_chat_target(None, "随便聊聊"))
    assert colleague["role_key"] == "assistant" and dispatch is None


def test_handoff_hint_contract(monkeypatch):
    """私聊转接建议提示：只列名册事实（与判官共用单源），不含自己；转接纪律归员工自身提示词。"""
    from app.services import colleague_turn_service as turns
    _patch_cfg(monkeypatch)
    hint = turns._handoff_hint({"role_key": "assistant"})
    assert "在册同事（职责与技能参考）" in hint
    assert "成本核算" in hint and "整机成本测算" in hint      # 名册职责进提示
    assert "技术支持工程师" in hint
    assert "总助" not in hint                                   # 自己（assistant 开场白）不进建议名单
    assert "一律自己完成" not in hint   # 纪律句已随「提示词（高级）」退役，不再从配置桶注入
    # 孤单角色（名册只有自己）→ 不出现空提示块
    _patch_cfg(monkeypatch, {"colleagues": [
        {"role_key": "solo", "name": "独行侠", "enabled": True, "dispatchable": True}]})
    assert turns._handoff_hint({"role_key": "solo"}) == ""


def test_capability_follows_skill_binding(monkeypatch):
    """2026-08-30 用户铁律：skill 绑定=能力，能力跟数据走不跟角色走。

    绑了 workflow skill 的角色（无论方案助手还是技术支持工程师）才走对话脑；
    解绑即失去能力（回落普通对话）——不许出现「某角色天生会配置」的代码定制。
    """
    from app.services import colleague_turn_service as turns
    from app.services import colleague_prompt
    monkeypatch.setattr(
        colleague_prompt, "_skill_library",
        lambda: {"requirement_analysis": {
            "key": "requirement_analysis", "type": "workflow", "workflow_key": "requirement_analysis"}})
    bound = {"role_key": "assistant", "skills": ["requirement_analysis"]}
    assert turns._has_workflow_skills(bound) is True
    # 解绑 → 能力消失（同一角色，数据一改行为即变）
    assert turns._has_workflow_skills({"role_key": "assistant", "skills": []}) is False
    assert turns._has_workflow_skills({"role_key": "assistant"}) is False
    # 任何角色都一样（技术支持工程师 / 数据分析师……）
    assert turns._has_workflow_skills(
        {"role_key": "support_engineer", "skills": ["requirement_analysis"]}) is True
    assert turns._has_workflow_skills(
        {"role_key": "support_engineer", "skills": ["nonexistent"]}) is False
    # 非 workflow 类型技能（纯 prompt 技能）不触发对话脑
    monkeypatch.setattr(
        colleague_prompt, "_skill_library",
        lambda: {"prompt_only": {"key": "prompt_only", "type": "prompt"}})
    assert turns._has_workflow_skills({"role_key": "x", "skills": ["prompt_only"]}) is False
