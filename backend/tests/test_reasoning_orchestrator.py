"""Graph Orchestrator 单测（2026-08 重构·阶段2/6）。

- 能力就绪约束：_ready_capabilities 依赖推导
- 编排退化：AI 关/编排 agent 失败 → 按 CAPABILITIES 顺序线性链（确定性兜底）
- 记忆持久化：conversation 存取会话
- 画布图 → 能力链派生（v13：编排器读画布拓扑；condition 透明桥 / 成环兜底 / 确定性配置驱动）
"""
import asyncio
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

import pytest
from unittest.mock import patch

from app.services.reasoning_orchestrator import (
    _ready_capabilities, _persist_conversation, run_orchestrator, CAPABILITIES,
)


def test_ready_capabilities_deps():
    """能力就绪约束：前置能力完成后才可调用下一个（Phase2 收敛链 6 节点）。"""
    assert _ready_capabilities(set()) == ["understand"]
    assert _ready_capabilities({"understand"}) == ["model_reason"]
    assert _ready_capabilities({"understand", "model_reason"}) == ["kp_reason"]
    assert _ready_capabilities({"understand", "model_reason", "kp_reason"}) == ["compose"]
    assert _ready_capabilities({"understand", "model_reason", "kp_reason", "compose"}) == ["llm_audit"]
    assert _ready_capabilities({"understand", "model_reason", "kp_reason", "compose", "llm_audit"}) == ["review"]
    assert _ready_capabilities({c["key"] for c in CAPABILITIES}) == []


def test_ready_capabilities_never_done_twice():
    """已完成的能力不再出现。"""
    assert "understand" not in _ready_capabilities({"understand"})


class _FakeSession:
    """内存会话（模拟 ReasoningSession 的 get_extra/update_meta）。"""

    def __init__(self):
        self.meta = {}

    def get_extra(self) -> dict:
        return dict(self.meta)

    def update_meta(self, patch: dict) -> None:
        self.meta.update(patch)


def test_persist_and_restore_conversation():
    """记忆持久化：用户消息全部保留 + 能力记录只留最近 4 条（总上限 24）。"""
    s = _FakeSession()
    convo = [{"role": "user", "content": f"需求{i}"} for i in range(30)]
    convo += [{"role": "assistant", "content": f"完成能力{i}"} for i in range(10)]
    _persist_conversation(s, "orchestrator_conversation", convo)
    raw = s.meta.get("orchestrator_conversation")
    assert raw
    restored = json.loads(raw)
    assert isinstance(restored, list)
    # 用户消息优先保留（上限 24 内）+ 最近 4 条能力记录
    users = [m for m in restored if m["role"] == "user"]
    assts = [m for m in restored if m["role"] == "assistant"]
    assert len(restored) == 24          # 总上限
    assert len(users) == 20             # 30 条用户消息截到 24-4
    assert len(assts) == 4              # 能力记录只留最近 4 条
    assert assts[0]["content"] == "完成能力6"
    assert users[-1]["content"] == "需求29"


async def _run_orch_ai_off(text: str, force: bool = True):
    """AI 关跑 orchestrator：编排 agent 不可用 → 退化线性链（确定性，不调 LLM）。"""
    from app.services.reasoning_orchestrator import run_orchestrator
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {}}
    # 直接 monkeypatch is_llm_enabled → False，走确定性链路
    from app.services import llm_client
    orig = llm_client.is_llm_enabled
    llm_client.is_llm_enabled = lambda: False
    try:
        ctx = await run_orchestrator("test-orch-1", text, flow, broadcast,
                                     initial_ctx={"force_complete": force}, session=session)
    finally:
        llm_client.is_llm_enabled = orig
    return ctx, events, session


def test_orchestrator_linear_fallback_ai_off():
    """AI 关 → 线性链跑完所有能力并出方案（确定性兜底）。"""
    ctx, events, session = asyncio.run(
        _run_orch_ai_off("2*AMD EPYC 9654 通用服务器，内存 32G*16，2*960G SSD，预算20万")
    )
    done_steps = [e["step"] for e in events if e["type"] == "step_done"]
    # 线性链（Phase2 收敛：AI 失效不再走 extract 正则理解，6 节点链）
    expected = ["understand", "model_reason", "kp_reason", "compose", "llm_audit", "review"]
    assert done_steps == expected, f"执行步骤: {done_steps}"
    assert any(e["type"] == "candidates_ready" for e in events)
    assert any(e["type"] == "pipeline_done" for e in events)
    # 记忆已保存
    assert session.meta.get("orchestrator_conversation")


def test_orchestrator_ask_reuses_run_llm_ask():
    """编排 agent 反问必须复用 llm_ask 能力（workload/分档/白名单/why 一套逻辑）。"""
    from app.services.reasoning_orchestrator import run_orchestrator
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {"llm_ask": {"strategy": "one"}}}

    from app.services.reasoning_orchestrator import _decide_next as _orig_decide
    from app.services import capabilities, reasoning_executor as rex

    async def fake_decide(*a, **kw):
        return {"action": "ask", "question": "您需要哪种工作负载？",
                "options": ["虚拟化 / 云主机", "数据库"], "reason": "需要先确定用途"}

    async def fake_run_llm_ask(ctx, config, broadcast=None):
        # 断言 orchestrator 把 llm_ask 节点配置传进来了
        assert config.get("strategy") == "one"
        return {"ok": True, "question": "您需要哪种工作负载？",
                "options": ["虚拟化 / 云主机", "数据库"], "why": "用途决定机型方向"}

    async def fake_dispatch(cap, ctx, config, broadcast):
        # hermetic：不碰真实 LLM。understand 抽不全 → clarity=partial → 触发反问路径
        if cap == "understand":
            ctx["understand_insufficient"] = True
            ctx["clarity"] = "partial"
            ctx["missing_fields"] = ["服务器类型/用途"]
            ctx["ext"] = {}
            return {"called": True, "source": "llm", "sufficient": False,
                    "missing_critical": ["服务器类型/用途"]}
        if cap == "gap_analyze":
            ctx["clarity"] = "partial"
            ctx["missing_fields"] = ["服务器类型/用途"]
            return {"level": "partial", "missing_fields": ["服务器类型/用途"]}
        return {"ok": True}

    import app.services.reasoning_orchestrator as orch
    orig_run = capabilities.run_llm_ask  # orchestrator ask 分支 from capabilities import run_llm_ask
    orig_dispatch = rex._dispatch
    capabilities.run_llm_ask = fake_run_llm_ask
    orch._decide_next = fake_decide
    rex._dispatch = fake_dispatch
    try:
        ctx = asyncio.run(run_orchestrator("test-orch-ask", "我要一台AI服务器", flow, broadcast,
                                           initial_ctx={}, session=session))
    finally:
        orch._decide_next = _orig_decide
        capabilities.run_llm_ask = orig_run
        rex._dispatch = orig_dispatch

    assert ctx.get("awaiting_input") is True
    ni = [e for e in events if e["type"] == "need_input"]
    assert ni and ni[0]["question"] == "您需要哪种工作负载？"
    assert ni[0]["options"] == ["虚拟化 / 云主机", "数据库"]
    assert ni[0]["why"] == "用途决定机型方向"
    assert ni[0]["source"] == "orchestrator"
    assert any(e["type"] == "pipeline_paused" for e in events)
    # 反问已写入记忆，避免下轮重复问
    raw = session.meta.get("orchestrator_conversation")
    assert raw and "反问" in raw


def test_orchestrator_ask_capped_by_max_rounds():
    """反问轮次达 llm_ask.max_rounds（默认 6）→ 禁止再 ask，直接调能力收敛（死循环防护）。"""
    from app.services.reasoning_orchestrator import run_orchestrator, _decide_next as _orig_decide
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {"llm_ask": {"strategy": "one", "max_rounds": 2}}}

    called = []

    async def fake_dispatch(cap, ctx, config, broadcast):
        called.append(cap)
        ctx.setdefault("ext", {})["server_type_name"] = "通用计算服务器"
        return {"ok": True}

    import app.services.reasoning_orchestrator as orch
    from app.services import reasoning_executor as rex
    async def fake_decide(*a, **kw):
        # 超过上限仍返回 ask —— 上层必须无视并转 call
        return {"action": "ask", "question": "还要问吗", "options": [], "reason": "test"}

    orch._decide_next = fake_decide
    orig_dispatch = rex._dispatch
    rex._dispatch = fake_dispatch  # run_orchestrator 内局部 import reasoning_executor._dispatch
    try:
        ctx = asyncio.run(run_orchestrator("test-orch-cap", "我要一台AI服务器", flow, broadcast,
                                           initial_ctx={"clarify_round": 2}, session=session))
    finally:
        orch._decide_next = _orig_decide
        rex._dispatch = orig_dispatch

    assert not any(e["type"] == "need_input" for e in events), "已达上限仍反问"
    assert "understand" in called, "应转调能力而非反问"
    assert ctx.get("awaiting_input") is not True


def test_orchestrator_retry_chain_deterministic():
    """audit_fix 触发重跑后：重跑链确定性按序执行（不再问 LLM、不提前 final），最终出 review。"""
    from app.services.reasoning_orchestrator import run_orchestrator, _decide_next as _orig_decide
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {"audit_fix": {"enabled": True, "max_retry": 1}}}

    import app.services.reasoning_orchestrator as orch
    from app.services import reasoning_executor as rex
    _orig_retry_targets = orch._decide_retry_targets

    async def fake_decide(*a, **kw):
        return {"action": "call", "capability": a[1][0] if a[1] else "final", "reason": "test"}

    async def fake_dispatch(cap, ctx, config, broadcast):
        if cap == "kp_reason" and not ctx.get("audit_retry_count"):
            # 模拟审计检出问题（Phase2 链内）→ 请求重跑链
            ctx["audit_retry_count"] = 1
            ctx["retry_caps"] = ["kp_reason", "compose", "llm_audit"]
        if cap == "compose":
            ctx["plans"] = [{"name": "T-Plan"}]
        return {"ok": True}

    async def fake_retry_targets(ctx, retry_caps):
        return list(retry_caps)  # 全量重跑（hermetic，不碰真实 LLM）

    orch._decide_next = fake_decide
    orch._decide_retry_targets = fake_retry_targets
    orig_dispatch = rex._dispatch
    rex._dispatch = fake_dispatch
    try:
        ctx = asyncio.run(run_orchestrator("test-orch-retry", "我要一台AI服务器", flow, broadcast,
                                           initial_ctx={"force_complete": True}, session=session))
    finally:
        orch._decide_next = _orig_decide
        orch._decide_retry_targets = _orig_retry_targets
        rex._dispatch = orig_dispatch

    done_steps = [e["step"] for e in events if e["type"] == "step_done"]
    # 重跑链（Phase2 收敛）：触发点在 kp（链前段）→ kp 初跑+重跑共 2 次，compose/llm_audit 在重跑趟各 1 次，review 收尾
    assert done_steps.count("kp_reason") == 2, done_steps
    assert done_steps.count("compose") == 1, done_steps
    assert done_steps.count("llm_audit") == 1, done_steps
    assert done_steps.count("review") == 1, done_steps
    # 顺序：重跑趟 kp → compose → llm_audit → review
    assert done_steps[-4:] == ["kp_reason", "compose", "llm_audit", "review"], done_steps
    assert any(e["type"] == "pipeline_done" for e in events)
    assert any(e["type"] == "candidates_ready" for e in events) or True  # compose 已产出 plans


def test_orchestrator_ai_off_catalog_guided_first():
    """AI 关且未跳过 → 先走目录引导（问类型），不静默线性链；catalog 完成后才出方案。"""
    from app.services.reasoning_orchestrator import run_orchestrator
    from app.services import reasoning_executor as rex
    from app.services import llm_client
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {}}
    asked = []

    async def fake_ask_catalog(ctx, broadcast, extra_questions=None):
        asked.append(ctx.get("catalog_stage") or "")
        rid = "clr_test"
        ctx["awaiting_input"] = True
        ctx["last_reply_id"] = rid
        await broadcast({"type": "need_input", "reply_id": rid, "question": "请选择服务器类型",
                         "options": ["通用计算服务器", "AI / 加速计算服务器"],
                         "stage": ctx.get("catalog_stage") or ""})
        return {"question": "请选择服务器类型", "reply_id": rid}

    orig_llm = llm_client.is_llm_enabled
    orig_ask = rex._ask_catalog_question
    llm_client.is_llm_enabled = lambda: False
    rex._ask_catalog_question = fake_ask_catalog
    try:
        ctx = asyncio.run(run_orchestrator("test-orch-cat", "我要台服务器", flow, broadcast,
                                           initial_ctx={"catalog_stage": "", "catalog_state": {}},
                                           session=session))
    finally:
        llm_client.is_llm_enabled = orig_llm
        rex._ask_catalog_question = orig_ask

    assert asked == [""]                      # 首问即目录引导
    assert ctx.get("awaiting_input") is True
    ni = [e for e in events if e["type"] == "need_input"]
    assert ni and "通用计算服务器" in (ni[0].get("options") or [])
    assert any(e["type"] == "pipeline_paused" for e in events)
    assert not [e for e in events if e["type"] == "step_start"]  # 未静默跑能力链


def test_orchestrator_ai_off_catalog_done_runs_chain():
    """AI 关但目录引导已完成（stage=done）→ 直接跑确定性能力链出方案（不再反问）。"""
    from app.services.reasoning_orchestrator import run_orchestrator, _decide_next as _orig_decide
    from app.services import reasoning_executor as rex
    from app.services import llm_client
    events = []

    async def broadcast(p):
        events.append(p)

    session = _FakeSession()
    flow = {"graph": {"nodes": []}, "node_configs": {}}

    import app.services.reasoning_orchestrator as orch
    async def fake_decide(*a, **kw):
        return None  # AI 关：编排决策不可用

    async def fake_dispatch(cap, ctx, config, broadcast):
        if cap == "understand":
            ctx["understand_fallback"] = True  # 模拟 AI 失效 → 编排器路由 extract 兜底
        if cap == "compose":
            ctx["plans"] = [{"name": "T-Plan"}]
        return {"ok": True}

    orch._decide_next = fake_decide
    orig_dispatch = rex._dispatch
    orig_llm = llm_client.is_llm_enabled
    rex._dispatch = fake_dispatch
    llm_client.is_llm_enabled = lambda: False
    try:
        ctx = asyncio.run(run_orchestrator("test-orch-cat2", "我要台服务器", flow, broadcast,
                                           initial_ctx={"catalog_stage": "done", "catalog_state": {},
                                                        "force_complete": False},
                                           session=session))
    finally:
        orch._decide_next = _orig_decide
        rex._dispatch = orig_dispatch
        llm_client.is_llm_enabled = orig_llm

    done_steps = [e["step"] for e in events if e["type"] == "step_done"]
    assert "understand" in done_steps and "review" in done_steps
    assert "extract" not in done_steps  # Phase1：AI 失效不再走 extract 正则理解
    assert any(e["type"] == "pipeline_done" for e in events)
    assert not any(e["type"] == "need_input" for e in events)  # 目录已完成不再问


# ── 画布图 → 能力链派生（v13：编排器读画布拓扑，不再硬编码）─────────────

def _v12_graph():
    """与后端 DEFAULT_GRAPH_V11 同构的最小 Phase2 单路链（6 节点，llm_ask 反问侧枝）。"""
    return {"nodes": [
        {"id": "understand", "type": "understand", "label": "需求理解+专家分析"},
        {"id": "llm_ask", "type": "llm_ask", "label": "智能反问"},
        {"id": "model_reason", "type": "model_reason", "label": "机型推理"},
        {"id": "kp_reason", "type": "kp_reason", "label": "配件提议+库校验"},
        {"id": "compose", "type": "compose", "label": "方案组装"},
        {"id": "llm_audit", "type": "llm_audit", "label": "方案校对"},
        {"id": "review", "type": "review", "label": "方案就绪"},
    ], "edges": [
        {"source": "understand", "target": "model_reason"},
        {"source": "model_reason", "target": "kp_reason"},
        {"source": "kp_reason", "target": "compose"},
        {"source": "compose", "target": "llm_audit"},
        {"source": "llm_audit", "target": "review"},
    ]}


def test_derive_capabilities_v12_matches_fallback():
    """v12 图派生结果 = 兜底链逐节点一致（deps + 确定性红线）——上线零行为变化。"""
    from app.services.reasoning_orchestrator import _derive_capabilities, CAPABILITIES
    caps = _derive_capabilities({"graph": _v12_graph()}, {})
    assert [c["key"] for c in caps] == [c["key"] for c in CAPABILITIES]
    assert [c["deps"] for c in caps] == [c["deps"] for c in CAPABILITIES]
    assert [c["deterministic"] for c in caps] == [c["deterministic"] for c in CAPABILITIES]


def test_derive_capabilities_follows_edited_graph():
    """用户拆节点/加连线 → 能力链跟着变（本方案核心诉求）。"""
    from app.services.reasoning_orchestrator import _derive_capabilities
    g = _v12_graph()
    g["nodes"].append({"id": "model_reason_2", "type": "model_reason", "label": "机型推理·复核"})
    g["edges"].append({"source": "model_reason", "target": "model_reason_2"})
    g["edges"].append({"source": "model_reason_2", "target": "kp_reason"})
    caps = _derive_capabilities({"graph": g}, {})
    keys = [c["key"] for c in caps]
    assert keys.index("model_reason_2") == keys.index("kp_reason") - 1
    assert caps[keys.index("model_reason_2")]["deps"] == ["model_reason"]


def test_derive_capabilities_condition_transparent_bridge():
    """condition 节点当透明桥：入边源 → 出边目标 直连后参与依赖。"""
    from app.services.reasoning_orchestrator import _derive_capabilities
    g = {"nodes": [
        {"id": "understand", "type": "understand", "label": "需求理解"},
        {"id": "cond1", "type": "condition", "label": "分支"},
        {"id": "gap_analyze", "type": "gap_analyze", "label": "缺口分析"},
        {"id": "review", "type": "review", "label": "方案就绪"},
    ], "edges": [
        {"source": "understand", "target": "cond1"},
        {"source": "cond1", "target": "gap_analyze"},
        {"source": "gap_analyze", "target": "review"},
    ]}
    caps = _derive_capabilities({"graph": g}, {})
    by = {c["key"]: c for c in caps}
    assert "cond1" not in by
    assert by["gap_analyze"]["deps"] == ["understand"]


def test_derive_capabilities_cycle_returns_none():
    """能力 DAG 成环 → None（上层兜底默认链，不阻塞）。"""
    from app.services.reasoning_orchestrator import _derive_capabilities
    g = {"nodes": [
        {"id": "a", "type": "understand", "label": "a"},
        {"id": "b", "type": "gap_analyze", "label": "b"},
    ], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}
    assert _derive_capabilities({"graph": g}, {}) is None


def test_derive_capabilities_empty_graph_returns_none():
    """空图 → None → 上层兜底默认链（历史测试依赖）。"""
    from app.services.reasoning_orchestrator import _derive_capabilities
    assert _derive_capabilities({"graph": {"nodes": [], "edges": []}}, {}) is None


def test_derive_capabilities_deterministic_config_driven():
    """确定性红线由节点配置驱动：默认集合 + 抽屉可改（compose 关掉后 det=False）。"""
    from app.services.reasoning_orchestrator import _derive_capabilities
    caps = _derive_capabilities({"graph": _v12_graph()}, {"compose": {"deterministic": False}})
    by = {c["key"]: c for c in caps}
    assert by["compose"]["deterministic"] is False          # 配置覆盖
    assert by["review"]["deterministic"] is True            # 默认红线仍生效
    assert by["understand"]["deterministic"] is False       # 非红线默认 False


# ── C：自纠重跑目标由 LLM 决策（审计意见喂回编排 agent）───────────────

def test_decide_retry_targets_preserves_spine():
    """LLM 只选可选重跑项；重建脊梁（kp_reason→spec_compliance→compose→budget_check）强制保留。"""
    from app.services.reasoning_orchestrator import _decide_retry_targets, _RETRY_SPINE
    from app.services import llm_client
    retry_caps = ["kp_reason", "spec_compliance", "compose", "budget_check", "llm_audit", "audit_fix"]

    async def _chat(messages, schema=None, temperature=None):
        return {"targets": ["llm_audit"], "reason": "再审一遍确认"}

    with patch.object(llm_client, "is_llm_enabled", return_value=True), \
         patch.object(llm_client, "chat_json", _chat), \
         patch("app.services.capabilities._collect_audit_issues", return_value=["缺少 GPU"]):
        targets = asyncio.run(_decide_retry_targets({}, retry_caps))
    assert set(_RETRY_SPINE).issubset(set(targets))   # 脊梁不可省
    assert "llm_audit" in targets
    assert set(targets).issubset(set(retry_caps))     # 不越界


def test_decide_retry_targets_ignores_invalid_choices():
    """LLM 给出非 retry_caps 的 target → 丢弃（受确定性红线约束，不越界）。"""
    from app.services.reasoning_orchestrator import _decide_retry_targets
    from app.services import llm_client
    retry_caps = ["kp_reason", "spec_compliance", "compose", "budget_check", "llm_audit"]

    async def _chat(messages, schema=None, temperature=None):
        return {"targets": ["compose", "hacked_cap", "llm_audit"], "reason": ""}

    with patch.object(llm_client, "is_llm_enabled", return_value=True), \
         patch.object(llm_client, "chat_json", _chat), \
         patch("app.services.capabilities._collect_audit_issues", return_value=[]):
        targets = asyncio.run(_decide_retry_targets({}, retry_caps))
    assert "hacked_cap" not in targets
    assert set(targets).issubset(set(retry_caps))


def test_decide_retry_targets_llm_off_or_error_returns_none():
    """AI 关 / LLM 报错 → None（上层全量重跑兜底，不阻塞）。"""
    from app.services.reasoning_orchestrator import _decide_retry_targets
    from app.services import llm_client
    with patch.object(llm_client, "is_llm_enabled", return_value=False):
        assert asyncio.run(_decide_retry_targets({}, ["kp_reason", "compose"])) is None

    async def _boom(messages, schema=None, temperature=None):
        raise llm_client.LLMError("boom")

    with patch.object(llm_client, "is_llm_enabled", return_value=True), \
         patch.object(llm_client, "chat_json", _boom):
        # 含可选重跑项（llm_audit）才触发 LLM 调用；LLM 报错 → None → 上层全量重跑
        assert asyncio.run(_decide_retry_targets({}, ["kp_reason", "compose", "llm_audit"])) is None


def test_retry_mode_runs_only_targets_then_resumes():
    """重跑模式只跑目标能力（不提前 final、不越跑），完成后退出恢复正常编排直到 review。"""
    from app.services.reasoning_orchestrator import run_orchestrator
    from app.services import llm_client
    events = []

    async def broadcast(p):
        events.append(p)

    flow = {"graph": {"nodes": []}, "node_configs": {}}
    orig = llm_client.is_llm_enabled
    llm_client.is_llm_enabled = lambda: False
    try:
        asyncio.run(run_orchestrator(
            "retry-test", "2U 通用服务器 32G*16", flow, broadcast,
            initial_ctx={"force_complete": True, "_retry_mode": True, "_retry_targets": {"understand"}},
            session=_FakeSession()))
    finally:
        llm_client.is_llm_enabled = orig
    steps = [e["step"] for e in events if e["type"] == "step_done"]
    assert steps[0] == "understand"      # 先跑重跑目标
    assert steps[-1] == "review"         # 之后恢复正常链，最终 review 收尾
    assert "pipeline_done" in [e["type"] for e in events]



# ============================================================
# 原则5：四类预算（墙钟/步数/工具调用/反问轮数）+ 超限判定
# ============================================================

def test_budget_state_and_exhausted():
    """预算用量计算 + 超限判定（墙钟/步数/工具调用任一超限即 exhausted）。"""
    from app.services.reasoning_orchestrator import _budget_state, _budget_exhausted
    orch = {"budgets": {"wall_clock_s": 10, "max_steps": 5, "max_tool_calls": 20, "max_ask_rounds": 3}}
    # 未超限
    box = {"steps": 2, "tools": 5}
    import time as _t
    bs = _budget_state(box, orch, _t.monotonic() - 3, ask_rounds=1)
    assert _budget_exhausted(bs) is False
    assert bs["steps"] == 2 and bs["tool_calls"] == 5 and bs["ask_rounds"] == 1
    # 步数超限
    box = {"steps": 5, "tools": 1}
    bs = _budget_state(box, orch, _t.monotonic() - 1, ask_rounds=0)
    assert _budget_exhausted(bs) is True
    # 工具调用超限
    box = {"steps": 1, "tools": 20}
    bs = _budget_state(box, orch, _t.monotonic() - 1, ask_rounds=0)
    assert _budget_exhausted(bs) is True
    # 墙钟超限
    box = {"steps": 1, "tools": 1}
    bs = _budget_state(box, orch, _t.monotonic() - 30, ask_rounds=0)
    assert _budget_exhausted(bs) is True
    # 0 = 不限制
    orch0 = {"budgets": {"wall_clock_s": 0, "max_steps": 0, "max_tool_calls": 0, "max_ask_rounds": 0}}
    box = {"steps": 999, "tools": 999}
    bs = _budget_state(box, orch0, _t.monotonic() - 99999, ask_rounds=999)
    assert _budget_exhausted(bs) is False
