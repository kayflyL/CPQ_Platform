# -*- coding: utf-8 -*-
"""⑧ L2 验收演练：stub 宿主（审批形状合成应用）经内核跑通完整流——引擎不带 CPQ。

本文件 import 面只有引擎模块（transaction_engine；仓储读写 monkeypatch 内存化），
不 import 任何业务域模块：可审计的"换宿主"行为证据（终局判定标准 S4）。
审批形状刻意区别于报价（起草→人工审批→会签归档→出具），考内核原语够不够——
缺口如实记进本文件尾部注释（内核缺口清单），不装懂。
"""
import pytest

from app.services import transaction_engine as te

FLOW_KEY = "stub.contract_approval"

RULES = {"rules": "合同审批流左栏纪律（合成）：审批必须人工拍板，AI 只陈述事实。",
         "steps": [
             {"key": "draft", "label": "起草合同申请", "tools": ["stub.draft_contract"],
              "completion": {"flag": "drafted"}},
             {"key": "review", "label": "人工审批", "tools": ["stub.approve_contract"],
              "completion": {"flag": "approved"}},
             {"key": "countersign", "label": "会签归档", "tools": ["stub.archive_contract"],
              "completion": {"flag": "archived"}},
             {"key": "issue", "label": "出具合同", "tools": ["stub.issue_contract"],
              "completion": {"flag": "issued"}},
         ],
         "edges": [],
         "flag_rules": [
             {"tool": "stub.draft_contract",
              "set": {"drafted": {"contract_id": "$result.contract_id"}}},
             {"tool": "stub.approve_contract",
              "set": {"approved": {"approver": "$result.approver"}}},
             {"tool": "stub.archive_contract",
              "set": {"archived": {"archive_no": "$result.archive_no"}}},
             {"tool": "stub.issue_contract",
              "set": {"issued": {"issue_no": "$result.issue_no"}}},
         ]}

USER = {"user_id": "u_stub", "name": "审批员"}


class StubApprovalHost:
    """合成审批宿主：TransactionApp 协议最小实现（flow_key/state_slot/context_fn/digest_lines）。"""

    flow_key = FLOW_KEY
    state_slot = "stub_state"

    def context_fn(self, thread_id, user):
        return {"合同": "《合成框架合同》", "申请人": str((user or {}).get("name") or "未知")}

    def digest_lines(self, view: dict) -> list:
        flags = view.get("flags") or {}
        lines = []
        if flags.get("drafted"):
            lines.append(f"已起草：合同 {flags['drafted'].get('contract_id')}")
        if flags.get("approved"):
            lines.append(f"已审批：{flags['approved'].get('approver')}")
        if flags.get("archived"):
            lines.append(f"已归档：{flags['archived'].get('archive_no')}")
        if flags.get("issued"):
            lines.append(f"已出具：{flags['issued'].get('issue_no')}")
        return lines


@pytest.fixture
def stub_world(monkeypatch):
    """离线假世界：状态槽内存化 + 流配置注入（不触任何仓储）。"""
    store = {}

    def _load(app, thread_id, role_key="assistant"):
        key = (thread_id, (role_key or "assistant"))
        return dict(store.get(key) or {})

    def _save(app, thread_id, role_key, state):
        store[(thread_id, (role_key or "assistant"))] = dict(state)

    monkeypatch.setattr(te, "load_state", _load)
    monkeypatch.setattr(te, "save_state", _save)
    monkeypatch.setattr(te, "load_flow_rules",
                        lambda key: dict(RULES) if key == FLOW_KEY else {"rules": "", "steps": []})
    app = StubApprovalHost()
    te.register(app)
    yield app, store
    te._APPS.pop(FLOW_KEY, None)


def _fact(tool: str, **result) -> dict:
    return {"tool": tool, "result": {"ok": True, **result}}


def test_stub_host_full_walk(stub_world):
    """完整流走通：起草→审批→会签→出具，指针单调推进到 complete，案台摘要全量。"""
    app, store = stub_world
    # 起点：指针在 draft，未完成
    v0 = te.state_view(app, "t_l2", "assistant", USER)
    assert v0["flow"]["steps"][0]["key"] == "draft"
    assert not v0.get("complete")
    # ① 起草（宿主工具事实 → 旗标表回写）
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.draft_contract", contract_id="C-001")])
    v1 = te.state_view(app, "t_l2", "assistant", USER)
    assert (v1.get("flags") or {}).get("drafted", {}).get("contract_id") == "C-001"
    # ② 人工审批（拍板人进旗标）
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.approve_contract", approver="审批员")])
    # ③ 会签归档
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.archive_contract", archive_no="A-2026-001")])
    # ④ 出具
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.issue_contract", issue_no="I-777")])
    v4 = te.state_view(app, "t_l2", "assistant", USER)
    assert v4.get("complete") is True, "四步事实齐 → 流必须判完成"
    # 案台摘要：宿主 digest_lines 被内核消费
    d = te.digest(app, v4)
    assert "已起草" in d and "C-001" in d, "案台摘要必须携带宿主域事实"
    assert "已出具" in d and "I-777" in d
    # 注册表解析（分发层按 flow_key 找到宿主）
    assert te.resolve_app(FLOW_KEY).flow_key == FLOW_KEY


def test_stub_host_incomplete_not_done(stub_world):
    """审批没拍板（缺 approved 旗标）→ 流不得判完成（人工闸语义）。"""
    app, store = stub_world
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.draft_contract", contract_id="C-002")])
    v = te.state_view(app, "t_l2", "assistant", USER)
    assert not v.get("complete"), "只起草未审批，不得判完成"


def test_stub_host_isolated_from_other_apps(stub_world):
    """应用分槽隔离：stub 的状态不串到其他 flow_key（换宿主不互相踩）。"""
    app, store = stub_world
    te.apply_facts(app, "t_l2", "assistant",
                   [_fact("stub.draft_contract", contract_id="C-003")])
    v = te.state_view(app, "t_other_thread_same_slot", "assistant", USER)
    assert not (v.get("flags") or {}).get("drafted"), "不同线程状态必须隔离"


# ── 内核缺口清单（审批形状演练的如实记录，供真实 APP#2 立项评估）──────────────
# 1. 通知原语：内核没有"通知/提醒"原语（审批该催人时，宿主要自建通知通道——
#    CPQ 已有 notification_hub；内核化需抽象一个 notification 端口）。
# 2. 审批链原语：多级审批（会签/或签/逐级）目前只能靠"多步+多旗标"拼，内核没有
#    一等审批原语；真实 APP#2 若审批层级复杂，需评估是否进内核。
# 3. 外部状态机：审批对象若在宿主系统里流转（合同系统状态机），内核只持有旗标
#    影子——探针/案台读宿主真相，本演练用合成事实代替（真实接入走探针 DSL）。
# 4. 定时触发：审批超时提醒需要调度原语（与"执行调度层缓做"决定同源，暂不补）。
