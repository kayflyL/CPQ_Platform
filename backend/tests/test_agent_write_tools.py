# -*- coding: utf-8 -*-
"""写操作工具单测：两阶段确认存证、身份 fail-closed、加价率重算口径、路由直调翻译。

全 mock（不碰 DB / LLM），pytest 跑，也可 `python -X utf8 tests/test_agent_write_tools.py` 自跑。
被测的 skill_tools_write.tool_* 是同步函数（handler 层负责 to_thread），直接调用。
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from app.services import agent_write_confirm as wc  # noqa: E402
from app.services import delivery_core as dcore  # noqa: E402
from app.services import skill_tools_write as sw  # noqa: E402
from app.services.skill_tool_context import TOOL_CTX  # noqa: E402


def _set_ctx(**overrides):
    ctx = {
        "role_key": "assistant", "price_ok": True, "thread_id": "th-1",
        "opportunity_id": "OPP-1", "user_id": "u-1",
        "user": {"user_id": "u-1", "name": "张三", "role": "admin"},
        "workflow_offers": [],
    }
    ctx.update(overrides)
    return TOOL_CTX.set(ctx)  # 调用方 finally: TOOL_CTX.reset(token)


# ── agent_write_confirm：待确认记录生命周期（按参数摘要匹配，无凭据往返）────


@pytest.fixture(autouse=True)
def _memory_confirm_store():
    """待确认记录走内存后端（生产默认落库 reasoning_state——活过 --reload/重启）。"""
    wc._STORAGE = "memory"
    wc._MEM.clear()
    yield
    wc._MEM.clear()


def test_confirm_stage_and_consume_happy_path():
    """主路径（无兼容口）：stage → 用户说话 → resolve 放行（参数以 staged 为准）
    → 成功 consume 销记录 → 再查 no_pending。"""
    args = {"sheet_id": 3, "opportunity_id": "OPP-1"}
    wc.stage("th", "submit_cost_sheet", args)
    wc.note_user_message("th")
    ok, exec_args, _note = wc.resolve_confirmed("th", "submit_cost_sheet", dict(args, confirm=True))
    assert ok and exec_args["sheet_id"] == 3
    wc.consume("th", "submit_cost_sheet")
    ok2, _a, note2 = wc.resolve_confirmed("th", "submit_cost_sheet", dict(args, confirm=True))
    assert not ok2 and note2 == "no_pending"


def test_confirm_number_normalization():
    """模型两次传参 15 vs 15.0 属同一参数：归一后摘要一致（strict 命中，无漂移说明）。"""
    wc.stage("th", "set_quote_margin", {"margin_pct": 15})
    wc.note_user_message("th")
    ok, exec_args, note = wc.resolve_confirmed("th", "set_quote_margin",
                                               {"margin_pct": 15.0, "confirm": True})
    assert ok and exec_args["margin_pct"] == 15 and not note


def test_confirm_value_drift_executes_staged():
    """值漂移重放 → 照常放行但执行参数 = staged（用户批准的那份），并给漂移说明；
    记录保留（成功才消费）。"""
    wc.stage("th", "submit_cost_sheet", {"sheet_id": 3})
    wc.note_user_message("th")
    ok, exec_args, note = wc.resolve_confirmed("th", "submit_cost_sheet",
                                               {"sheet_id": 4, "confirm": True})
    assert ok and exec_args["sheet_id"] == 3 and note
    assert wc.pending_count("th") == 1


def test_confirm_records_are_per_tool():
    """记录按工具分账：A 工具的记录不会被 B 工具的确认命中。"""
    wc.stage("th", "set_quote_margin", {"sheet_id": 3})
    wc.note_user_message("th")
    ok, _a, note = wc.resolve_confirmed("th", "submit_cost_sheet", {"sheet_id": 3, "confirm": True})
    assert not ok and note == "no_pending"


def test_confirm_loose_match_tolerates_drift():
    """字符串形态/多带键/漏带空值键 = 同一份预览（loose 命中，无漂移说明）；
    值真变了仍放行但给漂移说明且记录保留（执行参数照旧 staged）。"""
    wc.stage("th2", "submit_cost_sheet", {"sheet_id": 345, "opportunity_id": "OPP-1",
                                          "assignee_name": ""})
    wc.note_user_message("th2")
    ok, exec_args, note = wc.resolve_confirmed(
        "th2", "submit_cost_sheet", {"sheet_id": "345", "opportunity_id": "OPP-1", "confirm": True})
    assert ok and exec_args["sheet_id"] == 345 and not note
    wc.stage("th3", "submit_cost_sheet", {"sheet_id": 345})
    wc.note_user_message("th3")
    ok2, _a, note2 = wc.resolve_confirmed("th3", "submit_cost_sheet", {"sheet_id": 346, "confirm": True})
    assert ok2 and note2  # 值漂移给说明
    assert wc.pending_count("th3") == 1  # 记录保留


def test_confirm_requires_user_seen():
    """确认必须来自用户在预览之后真实说过的话——防大脑同一回合自问自答吃掉确认
    （2026-10-22 实锤：问"执行还是先补价"后 momentum 补 confirm 自批）。"""
    wc.stage("tA", "set_quote_margin", {"margin_pct": 13})
    # stage 后没有新用户消息（大脑同回合补 confirm）→ 拒，记录保留
    ok, _args, note = wc.resolve_confirmed("tA", "set_quote_margin",
                                           {"margin_pct": 13, "confirm": True})
    assert not ok and note == "confirm_not_from_user"
    assert wc.pending_count("tA") == 1
    # 用户在预览之后说过话 → 放行，执行参数 = staged（用户看过的那份）；漂移给说明
    wc.note_user_message("tA")
    ok, exec_args, note = wc.resolve_confirmed("tA", "set_quote_margin",
                                               {"margin_pct": 13.5, "confirm": True})
    assert ok and note
    assert exec_args["margin_pct"] == 13  # 重放漂到 13.5，落库仍按预览 13


def test_confirm_staged_exec_on_value_drift():
    """重放的非关键值与预览不同 → 照常执行但参数以 staged 为准，并给漂移说明。"""
    wc.stage("tB", "submit_cost_sheet", {"sheet_id": 7, "opportunity_id": "OPP-9"})
    wc.note_user_message("tB")
    ok, exec_args, note = wc.resolve_confirmed("tB", "submit_cost_sheet",
                                               {"sheet_id": 8, "opportunity_id": "OPP-9",
                                                "confirm": True})
    assert ok and exec_args["sheet_id"] == 7 and note  # 值差异给漂移说明
    # resolve 不再先销记录（2026-10-22 架构修：成功才消费）——重试仍放行，参数同 staged
    ok2, exec_args2, _n2 = wc.resolve_confirmed("tB", "submit_cost_sheet",
                                                {"sheet_id": 8, "opportunity_id": "OPP-9",
                                                 "confirm": True})
    assert ok2 and exec_args2["sheet_id"] == 7
    assert wc.pending_count("tB") == 1
    wc.consume("tB", "submit_cost_sheet")
    assert wc.pending_count("tB") == 0


def test_confirm_expiry():
    args = {"margin_pct": 15}
    wc.stage("th2", "set_quote_margin", args)
    bucket = wc._load_bucket("th2")
    bucket["records"]["set_quote_margin"]["expires_at"] = 0  # 过期时间拨到过去
    wc._save_bucket("th2", bucket)
    ok, _a, note = wc.resolve_confirmed("th2", "set_quote_margin", dict(args, confirm=True))
    assert not ok and note == "no_pending"
    assert wc.pending_count("th2") == 0  # 过期记录装载时清扫


def test_deferred_ledger_replay_once():
    """R3a 推迟账本：同工具同参数幂等记账；参数漂移=新的一笔（覆盖）；
    重放消费一次即清（成败都清，pop 幂等）。"""
    wc.defer_call("tL", "import_cost_sheet", {"attachment_id": "att1"})
    wc.defer_call("tL", "import_cost_sheet", {"attachment_id": "att1"})  # 幂等
    assert list(wc.deferred_calls("tL")) == ["import_cost_sheet"]
    wc.defer_call("tL", "import_cost_sheet", {"attachment_id": "att2"})  # 漂移覆盖
    assert wc.deferred_calls("tL")["import_cost_sheet"] == {"attachment_id": "att2"}
    wc.pop_deferred("tL", "import_cost_sheet")
    assert wc.deferred_calls("tL") == {}
    wc.pop_deferred("tL", "import_cost_sheet")  # 幂等


def test_confirm_card_is_projection_of_record():
    """授权问询是待确认记录的投影（2026-10-22 实锤「一口气两张一样的确认卡」）：
    同参重发沿用 query_opened（不发新问）；参数漂移=预览变了，归零重发；
    水位 seq 随重发更新（typed 确认闸仍认 stage 之后的用户消息）。"""
    args = {"sheet_id": 355}
    wc.stage("tC", "submit_cost_sheet", args, {"动作": "提交"})
    assert not wc.query_opened("tC", "submit_cost_sheet")
    wc.mark_query_opened("tC", "submit_cost_sheet")
    assert wc.query_opened("tC", "submit_cost_sheet")
    # 大脑同回合把工具调了第二次（同参数）→ 记录覆盖但标记保留
    wc.stage("tC", "submit_cost_sheet", dict(args), {"动作": "提交"})
    assert wc.query_opened("tC", "submit_cost_sheet")
    # 重发后 seq 刷成当前水位：用户随后说话仍可 typed 确认
    wc.note_user_message("tC")
    wc.stage("tC", "submit_cost_sheet", dict(args), {"动作": "提交"})
    bucket = wc._load_bucket("tC")
    assert bucket["records"]["submit_cost_sheet"]["seq"] == 1
    # 参数漂移 → 旧问作废，允许发新问
    wc.stage("tC", "submit_cost_sheet", {"sheet_id": 356}, {"动作": "提交"})
    assert not wc.query_opened("tC", "submit_cost_sheet")


def test_consent_query_and_ask_share_one_open_slot():
    """问答协议不变量：每线程至多一个开放问题——consent（调和器发起）与
    ask_user（大脑发起）共用同一槽位，第二问=契约错误（规则 12 的机制化）。"""
    import pytest
    from app.services import human_query as hq

    hq._STORAGE = "memory"
    hq._MEM.clear()
    try:
        hq.open_query("tH", kind="consent", title="待确认操作",
                      options=[{"label": "确认执行"}, {"label": "取消"}])
        with pytest.raises(hq.ContractError):
            hq.open_query("tH", kind="choice", title="另一个问题",
                          options=[{"label": "A"}, {"label": "B"}])
        # 关键形状校验：options/fields 都不给=纯文本问，不立问题
        kind, err = hq.validate_payload("问句", None, None)
        assert kind is None and err
        kind, err = hq.validate_payload("问句", [{"label": "A"}, {"label": "B"}], None)
        assert kind == "choice" and not err
        kind, err = hq.validate_payload("问句", None, [{"key": "k", "label": "K"}])
        assert kind == "form" and not err
        # 回答→关闭→可再问；take 取走即清
        r = hq.answer_query("tH", query_id=hq.open_query_of("tH")["query_id"],
                            selections=["确认执行"], answered_by="u1")
        assert r["answer"]["selections"] == ["确认执行"]
        assert hq.open_query_of("tH") is None
    finally:
        hq._MEM.clear()


# ── 身份 fail-closed 与公共小件 ───────────────────────────────────────


def test_tools_refuse_without_user_context():
    token = TOOL_CTX.set({"role_key": "assistant", "thread_id": "th", "price_ok": True})
    try:
        out = sw.tool_create_opportunity({"customer_name": "客户A"})
        assert out["ok"] is False and "身份" in out["error"]
        out = sw.tool_set_quote_margin({"margin_pct": 10})
        assert out["ok"] is False
    finally:
        TOOL_CTX.reset(token)


def test_call_route_translates_http_exception():
    def boom():
        raise HTTPException(status_code=409, detail="流程尚未进入该阶段")
    out = dcore.call_route(boom)
    assert out == {"ok": False, "error": "流程尚未进入该阶段", "status": 409}


def test_price_gate_refuses_without_price_ok():
    token = _set_ctx(price_ok=False)
    try:
        out = sw.tool_set_quote_margin({"margin_pct": 15})
        assert out["ok"] is False and "价格权限" in out["error"]
    finally:
        TOOL_CTX.reset(token)


# ── create_opportunity：路由直调 + 结果 digest ────────────────────────


def test_create_opportunity_calls_route_and_digests():
    """建档直接执行（2026-10-18 人工测试定调）：客户/归属已明确时不再出预览轮次，
    确认闸只保留在提交/加价两处。开工单表单本身就是参数确认。"""
    token = _set_ctx()
    try:
        with patch("app.api.opportunities.create_empty_opportunity",
                   return_value={"status": "success", "opportunity_id": "OPP-X"}) as mock_route, \
             patch("app.repository.assistant_repo.AssistantRepository") as mock_repo:
            first = sw.tool_create_opportunity({"customer_name": " 华为 ", "sales_person": "李四"})
            assert first.get("ok") is True
            assert first["opportunity_id"] == "OPP-X"
            assert mock_route.called
            req = mock_route.call_args.args[0]
            assert req.customer_name == "华为" and req.sales_person == "李四"
            out = sw.tool_create_opportunity(
                {"customer_name": "华为", "sales_person": "李四", "confirm": True})
        assert out["ok"] is True and out["opportunity_id"] == "OPP-X"
        assert out["note"]
        # real_bound：建档成功即把会话绑定到真实商机
        instance = mock_repo.return_value
        assert instance.update_thread_opportunity_id.called
        assert instance.update_thread_opportunity_id.call_args.args[1] == "OPP-X"
    finally:
        TOOL_CTX.reset(token)


def test_create_opportunity_requires_customer_name():
    token = _set_ctx()
    try:
        out = sw.tool_create_opportunity({"customer_name": "  "})
        assert out["ok"] is False and "customer_name" in out["error"]
    finally:
        TOOL_CTX.reset(token)


def test_create_opportunity_asks_sales_person_before_execute():
    """非 business 角色缺归属业务：执行前就要问（直接执行，不再有预览轮次）。"""
    token = _set_ctx(user={"user_id": "u-1", "name": "张三", "role": "admin"})
    try:
        out = sw.tool_create_opportunity({"customer_name": "华为"})
        assert out.get("needs_input") is True and out["missing"] == ["sales_person"]
        # 拿到姓名后直接建档成功
        with patch("app.api.opportunities.create_empty_opportunity",
                   return_value={"status": "success", "opportunity_id": "OPP-Y"}),              patch("app.repository.assistant_repo.AssistantRepository"):
            out2 = sw.tool_create_opportunity({"customer_name": "华为", "sales_person": "Frank"})
        assert out2.get("ok") is True and out2["opportunity_id"] == "OPP-Y"
    finally:
        TOOL_CTX.reset(token)


def test_create_opportunity_sales_ask_contract_off_disables_gate():
    """契约驱动反问：目标层 fields.sales_person.ask=false → 缺归属不再反问，
    建档放行（归属规则交回路由层兜底）。配置者关开关，反问即消失。"""
    fields = [{"key": "customer_name", "label": "客户名称", "ask": True},
              {"key": "sales_person", "label": "归属业务", "ask": False}]
    token = _set_ctx(user={"user_id": "u-1", "name": "张三", "role": "admin"},
                     step_fields=fields)
    try:
        with patch("app.api.opportunities.create_empty_opportunity",
                   return_value={"status": "success", "opportunity_id": "OPP-Z"}),              patch("app.repository.assistant_repo.AssistantRepository"):
            out = sw.tool_create_opportunity({"customer_name": "华为"})
        assert out.get("ok") is True and out["opportunity_id"] == "OPP-Z"
    finally:
        TOOL_CTX.reset(token)


def test_create_opportunity_sales_ask_contract_on_keeps_gate():
    """契约 ask=true（或无契约，缺省必填）：反问行为与收编前一致。"""
    fields = [{"key": "customer_name", "label": "客户名称", "ask": True},
              {"key": "sales_person", "label": "归属业务", "ask": True}]
    token = _set_ctx(user={"user_id": "u-1", "name": "张三", "role": "admin"},
                     step_fields=fields)
    try:
        out = sw.tool_create_opportunity({"customer_name": "华为"})
        assert out.get("needs_input") is True and out["missing"] == ["sales_person"]
    finally:
        TOOL_CTX.reset(token)


# ── set_quote_margin：重算口径镜像 + 两阶段确认 ───────────────────────


class _FakeItem:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return dict(self._d)


def _fake_quotation():
    return SimpleNamespace(
        quotation_id="QUO-1", opportunity_id="OPP-1", version=1,
        quotation_name="报价-华为-CFG1", source="worktable", status="active",
        total_qty=2, config_relation="compose", primary_config="CFG1",
        config_warranty_info={},
        extra_fields=json.dumps({"config_l6_picks": {
            "CFG1": {"l6_custom_price": 1000, "l6_profit_margin": 10},
        }}),
    )


def _fake_items():
    return [
        _FakeItem({"item_id": 1, "quotation_id": "QUO-1", "config_name": "CFG1",
                   "category": "Key Parts", "catalogue": "CPU-X", "description": "",
                   "part_category": "", "qty": 2, "base_price": 100,
                   "final_price": 110.0, "profit_margin": 10, "currency": "RMB",
                   "price_set_at": None}),
        _FakeItem({"item_id": 2, "quotation_id": "QUO-1", "config_name": "CFG1",
                   "category": "Warranty", "catalogue": "维保", "description": "",
                   "part_category": "", "qty": 1, "base_price": 50,
                   "final_price": 50.0, "profit_margin": 0, "currency": "RMB",
                   "price_set_at": None}),
    ]


def _margin_repo_mocks(quotation=None, items=None):
    quotation = quotation or _fake_quotation()
    items = items if items is not None else _fake_items()
    repo = MagicMock()
    repo.get_by_id.return_value = quotation
    repo.get_by_opportunity.return_value = [quotation]  # version 倒序首位的「最新单」
    repo.get_items.return_value = items
    repo.close.return_value = None
    return repo


def _run_margin(args):
    return sw.tool_set_quote_margin(args)


def test_set_quote_margin_two_phase_and_math():
    token = _set_ctx()
    try:
        repo = _margin_repo_mocks()
        saved_payload = {}

        def _fake_save(qid, data, user):
            saved_payload.update(data)
            return {"saved": len(data["items"])}

        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.api.deps.ensure_quotation_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository",
                   return_value=_FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])), \
             patch("app.repository.quotation_repo.QuotationRepository", return_value=repo), \
             patch("app.api.quotations.save_quotation_items", side_effect=_fake_save), \
             patch.object(dcore, "financial_rates", return_value=(7.0, 0.13)):
            first = _run_margin({"margin_pct": 20})
            # 第一阶段：只出预览，不写库
            assert first.get("needs_confirmation") is True and "confirm_token" not in first
            before_top = first["preview"]["整单快照（主配置）"]["改前"]
            assert before_top["total_price"] == 1370.0   # 1100(L6) + 220(KP) + 50(维保)
            assert before_top["profit_margin"] == 9.6    # 120 / 1250
            assert not saved_payload

            wc.note_user_message("th-1")
            second = _run_margin({"margin_pct": 20, "confirm": True})
        assert second["ok"] is True and second["quotation_id"] == "QUO-1"
        # 行级：KP 行加价率=20、final=120；Warranty 行加价率不动、final 按自身口径重算=50
        items = saved_payload["items"]
        kp = next(i for i in items if i["category"] == "Key Parts")
        wty = next(i for i in items if i["category"] == "Warranty")
        assert kp["profit_margin"] == 20 and kp["final_price"] == 120.0
        assert wty["profit_margin"] == 0 and wty["final_price"] == 50.0
        assert "item_id" not in kp and "quotation_id" not in kp  # 不把行号灌进 extra_fields
        # L6：加价率=20、售价=1200；顶层快照=工作台口径
        assert saved_payload["config_l6_picks"]["CFG1"]["l6_profit_margin"] == 20
        assert saved_payload["total_price"] == 1490.0   # 1200 + 240 + 50
        assert saved_payload["profit_margin"] == 19.2   # 240 / 1250
        assert saved_payload["l6_price"] == 1200.0
    finally:
        TOOL_CTX.reset(token)


def test_set_quote_margin_confirm_first_call_rescued_to_preview():
    """机制性防绕过：没出过预览就带 confirm=true 首调 → 原地降级为预览+确认卡路径
    （2026-10-22 抢跑自愈：报错了事=用户等一张永远不来的卡），绝不执行；
    stage 之后有真实用户消息的 confirm 重调才执行。"""
    token = _set_ctx()
    try:
        repo = _margin_repo_mocks()
        saved_payload = {}
        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.api.deps.ensure_quotation_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository",
                   return_value=_FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])), \
             patch("app.repository.quotation_repo.QuotationRepository", return_value=repo), \
             patch("app.api.quotations.save_quotation_items",
                   side_effect=lambda qid, data, user: saved_payload.update(data) or {"saved": 0}), \
             patch.object(dcore, "financial_rates", return_value=(7.0, 0.13)):
            first = _run_margin({"margin_pct": 20, "confirm": True})
            assert first.get("needs_confirmation") is True and not saved_payload
            wc.note_user_message("th-1")
            second = _run_margin({"margin_pct": 20, "confirm": True})
        assert second["ok"] is True and second["quotation_id"] == "QUO-1"
        assert saved_payload
    finally:
        TOOL_CTX.reset(token)


def test_set_quote_margin_usd_row_uses_rate_and_tax():
    token = _set_ctx()
    try:
        quotation = _fake_quotation()
        items = [_FakeItem({"item_id": 1, "quotation_id": "QUO-1", "config_name": "CFG1",
                            "category": "Key Parts", "qty": 1, "base_price": 100,
                            "final_price": 0, "profit_margin": 0, "currency": "USD",
                            "price_set_at": None})]
        repo = _margin_repo_mocks(quotation, items)
        saved_payload = {}

        def _fake_save(qid, data, user):
            saved_payload.update(data)
            return {"saved": 1}

        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.api.deps.ensure_quotation_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository",
                   return_value=_FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])), \
             patch("app.repository.quotation_repo.QuotationRepository", return_value=repo), \
             patch("app.api.quotations.save_quotation_items", side_effect=_fake_save), \
             patch.object(dcore, "financial_rates", return_value=(7.0, 0.13)):
            first = _run_margin({"margin_pct": 10, "apply_to": "kp"})
            wc.note_user_message("th-1")
            second = _run_margin({"margin_pct": 10, "apply_to": "kp", "confirm": True})
        assert second["ok"] is True
        kp = saved_payload["items"][0]
        # USD 行成本 = 100×7.0×1.13 = 791；加价10% → final = 870.1
        assert kp["final_price"] == 870.1
        # apply_to=kp 不动 L6 加价率
        assert saved_payload["config_l6_picks"]["CFG1"]["l6_profit_margin"] == 10
    finally:
        TOOL_CTX.reset(token)


def test_set_quote_margin_default_picks_latest_active_quotation():
    token = _set_ctx()
    try:
        quotation = _fake_quotation()
        repo = _margin_repo_mocks(quotation)
        repo.get_by_opportunity.return_value = [quotation]
        opp_repo = _FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])
        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.api.deps.ensure_quotation_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository", return_value=opp_repo), \
             patch("app.repository.quotation_repo.QuotationRepository", return_value=repo), \
             patch("app.api.quotations.save_quotation_items", return_value={"saved": 0}), \
             patch.object(dcore, "financial_rates", return_value=(7.0, 0.13)):
            out = _run_margin({"opportunity_id": "OPP-1", "margin_pct": 5})
        assert out.get("needs_confirmation") is True
        assert out["preview"]["报价单"].startswith("报价-华为-CFG1")
    finally:
        TOOL_CTX.reset(token)


# ── submit_cost_sheet：两阶段 + 提交/转换链 ───────────────────────────


def test_submit_cost_sheet_two_phase_then_calls_submit_and_convert():
    token = _set_ctx()
    try:
        sheet = {"id": 7, "name": "成本-底表", "status": "draft",
                 "configs": [{"name": "CFG1"}]}
        flow_repo = MagicMock()
        flow_repo.get_cost_sheet.return_value = sheet
        flow_repo.close.return_value = None
        with patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo), \
             patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.api.portal.submit_cost_sheet",
                   return_value={"sheet": {}, "quotation_id": "QUO-9"}) as mock_submit, \
             patch("app.api.portal.convert_cost_to_quotation",
                   return_value={"ok": True, "quotation_id": "QUO-9"}) as mock_convert:
            first = sw.tool_submit_cost_sheet({"sheet_id": 7})
            assert first.get("needs_confirmation") is True
            assert not mock_submit.called

            wc.note_user_message("th-1")
            out = sw.tool_submit_cost_sheet({"sheet_id": 7, "confirm": True})
            assert out["ok"] is True and out["quotation_id"] == "QUO-9" and out["converted"] is True
            assert mock_submit.called and mock_convert.called

            # 非草稿拒绝提交（仍在 patch 作用域内，不触真库）
            flow_repo.get_cost_sheet.return_value = {**sheet, "status": "current"}
            out2 = sw.tool_submit_cost_sheet({"sheet_id": 7})
            assert out2["ok"] is False and "草稿" in out2["error"]
    finally:
        TOOL_CTX.reset(token)


# ── share_quote：customer 视角红线 + 正常路径 ─────────────────────────


def test_share_quote_refuses_customer_view():
    token = _set_ctx()
    try:
        out = sw.tool_share_quote({"view": "customer"})
        assert out["ok"] is False and "外发审批" in out["error"]
    finally:
        TOOL_CTX.reset(token)


def test_share_quote_creates_link():
    token = _set_ctx()
    try:
        quotation = _fake_quotation()
        repo = _margin_repo_mocks(quotation)
        repo.get_by_opportunity.return_value = [quotation]
        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.repository.quotation_repo.QuotationRepository", return_value=repo), \
             patch("app.api.artifact_share.create_artifact_share",
                   return_value={"share": {"token": "abc"}, "share_path": "/api/share/abc"}) as mock_create:
            out = sw.tool_share_quote({"expiry_days": 99})
        assert out["ok"] is True and out["share_path"] == "/api/share/abc"
        assert out["expiry_days"] == 30  # 上限钳制
        body = mock_create.call_args.args[1]
        assert body.source_id == "QUO-1" and body.view == "internal"
    finally:
        TOOL_CTX.reset(token)


# ── import_cost_sheet：附件选取守卫 / 暂存绑定 / archive_only / overrides ──


def _feed_repo_mock(list_attachments=None, get_attachment=None, staged=None):
    m = MagicMock()
    m.list_attachments.return_value = list_attachments or []
    m.list_staged_attachments.return_value = staged or []
    m.get_attachment.return_value = get_attachment
    m.bind_attachment.side_effect = lambda aid, **kw: {"attachment_id": aid, **kw}
    m.close.return_value = None
    return m


def test_import_cost_sheet_reports_missing_attachments():
    token = _set_ctx()
    try:
        feed_repo = _feed_repo_mock(list_attachments=[
            {"attachment_id": "a1", "opportunity_id": "OPP-1",
             "original_filename": "方案.pdf", "storage_key": "k1"}],
            staged=[])
        with patch("app.api.deps.ensure_opportunity_access",
                   return_value={"opportunity_id": "OPP-1", "customer_name": "华为"}), \
             patch("app.api.deps.user_has_permission", return_value=True), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo):
            out = sw.tool_import_cost_sheet({})
        assert out["ok"] is False and "表格附件" in out["error"]
    finally:
        TOOL_CTX.reset(token)


def test_import_cost_sheet_rejects_foreign_attachment():
    """分析模式可读本人可访问商机里的附件；不可访问的拒绝。"""
    token = _set_ctx()
    try:
        feed_repo = _feed_repo_mock(get_attachment={
            "attachment_id": "a2", "opportunity_id": "OPP-OTHER",
            "original_filename": "成本.xlsx", "storage_key": "k2"})
        with patch("app.api.deps.ensure_opportunity_access",
                   side_effect=HTTPException(status_code=403, detail="无权访问该商机")), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo):
            out = sw.tool_import_cost_sheet({"attachment_id": "a2"})
        assert out["ok"] is False and "无权访问" in out["error"]
    finally:
        TOOL_CTX.reset(token)


def test_import_analysis_only_without_target_saves_nothing():
    """无商机=仅解析预览：零落库零归档，结果带 analysis_only 标记与下一步指引。"""
    token = _set_ctx(opportunity_id="")
    try:
        staged_att = {"attachment_id": "a5", "opportunity_id": None,
                      "uploader_user_id": "u-1", "original_filename": "成本.xlsx",
                      "storage_key": "threads/th/x.xlsx", "file_size": 10}
        feed_repo = _feed_repo_mock(get_attachment=staged_att)
        flow_repo = MagicMock()
        flow_repo.save_cost_sheet_draft.side_effect = AssertionError("分析模式不许落草稿")
        flow_repo.close.return_value = None
        storage = MagicMock()
        storage.read_bytes.return_value = b"xx"

        class _Svc:
            def process_upload(self, content, filename, parse_overrides=None):
                return {"status": "ok", "configs": {"CFG1": {}}}

            def close(self):
                pass

        with patch("app.api.deps.user_has_permission", return_value=True), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo), \
             patch("app.services.storage_adapter.get_storage", return_value=storage), \
             patch("app.services.quote_service.QuoteService", return_value=_Svc()), \
             patch("app.api.portal._parse_result_to_cost_configs",
                   return_value=[{"name": "CFG1", "server_model": "ZS22EV1-Z",
                                  "qty": 1, "kp_rows": [1, 2], "l6_cost": 0}]), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo):
            out = sw.tool_import_cost_sheet({"attachment_id": "a5"})
        assert out["ok"] is True and out["analysis_only"] is True
        assert out["configs"][0]["server_model"] == "ZS22EV1-Z"
        assert "仅解析预览" in out["note"]
        assert not flow_repo.save_cost_sheet_draft.called
        assert not feed_repo.bind_attachment.called
    finally:
        TOOL_CTX.reset(token)


def test_import_staged_attachment_binds_to_opportunity():
    """聊天框暂存件（NULL 商机）导入成功 → 原件归档进商机桶（改绑+移桶+删暂存）。"""
    token = _set_ctx()
    try:
        staged_att = {"attachment_id": "a9", "opportunity_id": None,
                      "uploader_user_id": "u-1", "original_filename": "成本.xlsx",
                      "storage_key": "threads/th/x.xlsx", "file_size": 10}
        feed_repo = _feed_repo_mock(get_attachment=staged_att)
        flow_repo = MagicMock()
        flow_repo.list_cost_sheets.return_value = []
        flow_repo.save_cost_sheet_draft.return_value = {"id": 5, "name": "成本-成本"}
        flow_repo.get_cost_sheet.return_value = None
        flow_repo.close.return_value = None
        saved = {}

        def _fake_save(opp_id, sid, name, configs, **kw):
            saved["args"] = (opp_id, sid, name)
            return {"id": 5, "name": name}

        storage = MagicMock()
        storage.read_bytes.return_value = b"xx"
        storage.save_bytes.return_value = "opportunities/华为_OPP-1/成本核算/x.xlsx"
        svc = MagicMock()
        svc.process_upload.return_value = {"status": "ok", "configs": {"CFG1": {}}}
        svc.close.return_value = None
        with patch("app.api.deps.ensure_opportunity_access",
                   return_value={"opportunity_id": "OPP-1", "customer_name": "华为"}), \
             patch("app.api.deps.user_has_permission", return_value=True), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo), \
             patch("app.services.storage_adapter.get_storage", return_value=storage), \
             patch("app.services.quote_service.QuoteService", return_value=svc), \
             patch("app.api.portal._parse_result_to_cost_configs",
                   return_value=[{"name": "CFG1", "kp_rows": [1], "l6_cost": 0}]), \
             patch("app.api.portal._attach_entity_card", return_value={"id": 1}), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo), \
             patch.object(sw, "_cost_sheet_name_guard", None, create=True):
            first = sw.tool_import_cost_sheet({"attachment_id": "a9"})
            # 先看后落：首调只出确认预览，不落草稿、不改绑暂存件
            assert first.get("needs_confirmation") is True
            assert not feed_repo.bind_attachment.called and not saved
            wc.note_user_message("th-1")
            out = sw.tool_import_cost_sheet({"attachment_id": "a9", "confirm": True})
        assert out["ok"] is True and out["sheet_id"] == 5
        # 暂存件被改绑进商机 + 换存储键 + 删暂存文件
        assert feed_repo.bind_attachment.called
        kw = feed_repo.bind_attachment.call_args.kwargs
        assert kw["opportunity_id"] == "OPP-1" and kw["category"] == "requirement"
        assert kw["storage_key"].startswith("opportunities/")
        assert storage.delete.called
        assert out["archived"]["category"] == "requirement"
    finally:
        TOOL_CTX.reset(token)


def test_import_archive_only_places_file_in_bucket():
    token = _set_ctx()
    try:
        staged_att = {"attachment_id": "a3", "opportunity_id": None,
                      "uploader_user_id": "u-1", "original_filename": "报告.pdf",
                      "storage_key": "threads/th/r.pdf", "file_size": 5}
        feed_repo = _feed_repo_mock(get_attachment=staged_att)
        storage = MagicMock()
        storage.read_bytes.return_value = b"pdf"
        storage.save_bytes.return_value = "opportunities/华为_OPP-1/BOM方案/r.pdf"
        with patch("app.api.deps.ensure_opportunity_access",
                   return_value={"opportunity_id": "OPP-1", "customer_name": "华为"}), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo), \
             patch("app.services.storage_adapter.get_storage", return_value=storage):
            out = sw.tool_import_cost_sheet(
                {"attachment_id": "a3", "archive_only": True, "category": "technical"})
        assert out["ok"] is True and out["category"] == "technical"
        kw = feed_repo.bind_attachment.call_args.kwargs
        assert kw["opportunity_id"] == "OPP-1" and kw["category"] == "technical"
    finally:
        TOOL_CTX.reset(token)


def test_import_parse_overrides_reused_in_place():
    """修正补丁透传给解析器；sheet_id 原地更新草稿；结果带固化提示。"""
    token = _set_ctx()
    try:
        att = {"attachment_id": "a1", "opportunity_id": "OPP-1",
               "uploader_user_id": "u-1", "original_filename": "成本.xlsx",
               "storage_key": "k1", "file_size": 10}
        feed_repo = _feed_repo_mock(get_attachment=att)
        flow_repo = MagicMock()
        flow_repo.get_cost_sheet.return_value = {"id": 5, "name": "成本-成本", "status": "draft"}
        overrides = {"skip_rows": [1, 2]}
        saved = {}

        def _fake_save(opp_id, sid, name, configs, **kw):
            saved["sheet_id"] = sid
            return {"id": sid or 5, "name": name}

        flow_repo.save_cost_sheet_draft.side_effect = _fake_save
        flow_repo.close.return_value = None

        storage = MagicMock()
        storage.read_bytes.return_value = b"xx"
        svc = MagicMock()
        svc_close = MagicMock()

        class _Svc:
            def process_upload(self, content, filename, parse_overrides=None):
                saved["overrides"] = parse_overrides
                return {"status": "ok", "configs": {"CFG1": {}}}

            def close(self):
                svc_close()

        with patch("app.api.deps.ensure_opportunity_access",
                   return_value={"opportunity_id": "OPP-1", "customer_name": "华为"}), \
             patch("app.api.deps.user_has_permission", return_value=True), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo), \
             patch("app.services.storage_adapter.get_storage", return_value=storage), \
             patch("app.services.quote_service.QuoteService", return_value=_Svc()), \
             patch("app.api.portal._parse_result_to_cost_configs",
                   return_value=[{"name": "CFG1", "kp_rows": [], "l6_cost": 0}]), \
             patch("app.api.portal._attach_entity_card", return_value={"id": 1}), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo):
            first = sw.tool_import_cost_sheet(
                {"attachment_id": "a1", "parse_overrides": overrides, "sheet_id": 5})
            assert first.get("needs_confirmation") is True and "sheet_id" not in saved
            wc.note_user_message("th-1")
            out = sw.tool_import_cost_sheet(
                {"attachment_id": "a1", "parse_overrides": overrides, "sheet_id": 5,
                 "confirm": True})
        assert out["ok"] is True
        assert saved["overrides"] == overrides
        assert saved["sheet_id"] == 5
        assert out.get("overrides_applied") is True
    finally:
        TOOL_CTX.reset(token)


# ── 自然标识解析：customer_name 精确 / 歧义 / 未命中 ───────────────────


class _FakeOppRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_opportunity(self, oid):
        for r in self._rows:
            if r["opportunity_id"] == oid:
                return r
        return None

    def list_opportunities(self, search=None, page_size=50, **kw):
        rows = [r for r in self._rows if search in (r.get("customer_name") or "")] if search else self._rows
        return rows, len(rows)

    def close(self):
        pass


def test_resolve_target_exact_name():
    rows = [{"opportunity_id": "OPP-A", "customer_name": "华为"}]
    with patch("app.repository.opportunity_repo.OpportunityRepository",
               return_value=_FakeOppRepo(rows)):
        out = dcore.resolve_opportunity({"user_id": "u"}, customer_name="华为")
    assert out["ok"] is True and out["opportunity_id"] == "OPP-A"


def test_resolve_target_ambiguous_returns_candidates():
    rows = [{"opportunity_id": "OPP-A", "customer_name": "华为技术"},
            {"opportunity_id": "OPP-B", "customer_name": "华为终端"}]
    with patch("app.repository.opportunity_repo.OpportunityRepository",
               return_value=_FakeOppRepo(rows)):
        out = dcore.resolve_opportunity({"user_id": "u"}, customer_name="华为")
    assert out["ok"] is False and len(out["candidates"]) == 2


def test_resolve_target_miss_suggests_create():
    with patch("app.repository.opportunity_repo.OpportunityRepository",
               return_value=_FakeOppRepo([])):
        out = dcore.resolve_opportunity({"user_id": "u"}, customer_name="不存在")
    assert out["ok"] is False and "新建商机" in out["error"]


# ── workflow_suggestion 落库 kind 修复回归 ────────────────────────────


def test_persist_broadcast_stamps_workflow_suggestion_kind():
    """带发起建议时 kind 必须落 workflow_suggestion，前端按 kind 渲染一键发起卡。"""
    import asyncio

    from app.services import colleague_turn_io

    recorded = {}

    class _FakeRepo:
        def add_message(self, **kwargs):
            recorded.update(kwargs)
            return {"message_id": "m1", "kind": kwargs.get("kind")}

        def close(self):
            pass

    async def _noop(*args, **kwargs):
        return None

    with patch("app.services.colleague_turn_io.AssistantRepository", return_value=_FakeRepo()), \
         patch.object(colleague_turn_io.assistant_hub, "broadcast", side_effect=_noop), \
         patch.object(colleague_turn_io, "publish_office_event", side_effect=_noop):
        asyncio.run(colleague_turn_io._persist_and_broadcast(
            "th", {"role_key": "assistant"}, "建议发起",
            workflow_suggestion={"workflow_key": "k", "requirement_text": "r"}))
        assert recorded["kind"] == "workflow_suggestion"
        asyncio.run(colleague_turn_io._persist_and_broadcast(
            "th", {"role_key": "assistant"}, "普通回复"))
        assert recorded["kind"] == "text"


# ── 确认卡：needs_confirmation 落 input_options 卡 ────────────────────


def test_consent_query_emitted_and_broadcast():
    """授权问询（consent HumanQuery）：非 confirm 结果原样透传不发问；
    confirm 结果立问（选项=确认执行/取消、action 绑定工具）并打 query_opened；
    轮壳 defer 时只返回不发射（先解释后问）。"""
    import asyncio

    from app.services import human_query as hq
    from app.services.agent_tool_handlers import _with_consent_query

    hq._STORAGE = "memory"
    hq._MEM.clear()
    token = TOOL_CTX.set({"role_key": "assistant", "thread_id": "th-card",
                          "user_id": "u-1", "price_ok": True})
    wc.stage("th-card", "submit_cost_sheet", {"sheet_id": 1}, {"动作": "提交"})
    fake_repo = MagicMock()
    fake_repo.add_message.return_value = {"message_id": "m1"}
    fake_repo.close.return_value = None
    try:
        # 展示副本的仓库 mock 掉（不写真库）
        with patch("app.repository.assistant_repo.AssistantRepository", return_value=fake_repo):
            # 非 confirm 结果：原样透传，不发问
            passthrough = asyncio.run(_with_consent_query({"ok": True}, tool="submit_cost_sheet"))
            assert passthrough == {"ok": True} and hq.open_query_of("th-card") is None
            # confirm 结果：立 consent 问（选项固定确认执行/取消）
            out = asyncio.run(_with_consent_query({
                "needs_confirmation": True, "confirm_token": "t1",
                "preview": {"动作": "提交成本表并转为报价单草稿",
                            "将发生": ["a", "b"]}}, tool="submit_cost_sheet"))
        assert out.get("needs_confirmation") is True  # 结果原样回大脑
        q = hq.open_query_of("th-card")
        assert q and q["kind"] == "consent" and q["action"]["tool"] == "submit_cost_sheet"
        assert [o["label"] for o in q["options"]] == ["确认执行", "取消"]
        assert "提交成本表" in q["question"]["detail"] and "a" not in q["question"]["detail"]
        assert wc.query_opened("th-card", "submit_cost_sheet")  # R1：记录已发射标记
        # 再来一次同参重发 → 不挤第二个问题（R1 投影幂等）
        with patch("app.repository.assistant_repo.AssistantRepository", return_value=fake_repo):
            asyncio.run(_with_consent_query({
                "needs_confirmation": True, "preview": {"动作": "提交"}},
                tool="submit_cost_sheet"))
        assert hq.open_query_of("th-card")["query_id"] == q["query_id"]
    finally:
        TOOL_CTX.reset(token)
        hq._MEM.clear()


# ── set_cost_prices：缺价补充回写（2026-10-22 缺价闸的聊天回价通道）────────


def test_set_cost_prices_writes_rows_and_reports_misses():
    """聊天回价 → 按 配置名+Catalogue 回写 base_price；方案挂接保留；对不上的行进 missed。"""
    token = _set_ctx()
    try:
        configs = [{"name": "CFG1", "kp_rows": [{"catalogue": "CPU", "base_price": 0}],
                    "l6_rows": [{"catalogue": "导轨", "base_price": None}]}]
        flow_repo = MagicMock()
        flow_repo.list_cost_sheets.return_value = [
            {"id": 7, "name": "成本-x", "status": "draft", "configs": configs,
             "bom_scheme_id": 3, "quotation_id": ""}]
        saved = {}

        def _fake_save(opp_id, sid, name, cs, **kw):
            saved.update(sheet_id=sid, bom_scheme_id=kw.get("bom_scheme_id"), configs=cs)
            return {"id": 7, "name": name}

        flow_repo.save_cost_sheet_draft.side_effect = _fake_save
        flow_repo.close.return_value = None
        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository",
                   return_value=_FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo):
            out = sw.tool_set_cost_prices({"prices": [
                {"config_name": "CFG1", "catalogue": " CPU ", "base_price": 120},
                {"config_name": "CFG1", "catalogue": "不存在的行", "base_price": 5}]})
        assert out["ok"] is True and out["sheet_id"] == 7
        assert saved["sheet_id"] == 7 and saved["bom_scheme_id"] == 3  # 原地更新且方案挂接不丢
        assert saved["configs"][0]["kp_rows"][0]["base_price"] == 120.0
        assert len(out["applied"]) == 1 and len(out["missed"]) == 1
        # 探针口径：补完 CPU 后 L6 仍缺 1 行
        from app.services.delivery_app import _missing_prices
        assert _missing_prices(saved["configs"], {"kp_price": True, "l6_price": True}) == \
            {"kp_missing": 0, "l6_missing": 1}
    finally:
        TOOL_CTX.reset(token)


def test_latest_cost_sheet_price_ready_by_strategy():
    """price_ready 按字段策略现算：KP 逐行；L6 按配置级整价（l6_cost，页面口径——
    l6_rows 只是明细）。未配置策略 → 不拦。"""
    from app.services import delivery_app as dapp
    configs = [
        {"name": "A", "l6_cost": 800, "kp_rows": [{"base_price": 5}],
         "l6_rows": [{"base_price": 0}]},
        {"name": "B", "l6_cost": 0, "kp_rows": [], "l6_rows": [{"base_price": 9}]},
    ]
    with patch("app.repository.flow_repo.FlowRepository") as FR:
        fr = FR.return_value
        fr.list_cost_sheets.return_value = [
            {"id": 1, "name": "s", "status": "draft", "configs": configs}]
        fr.close.return_value = None
        out = dapp._latest_cost_sheet("OPP-1", {"kp_price": True, "l6_price": True})
        out2 = dapp._latest_cost_sheet("OPP-1", {})
    assert out["kp_missing"] == 0 and out["l6_missing"] == 1 and out["price_ready"] is False
    assert out2["price_ready"] is True


def test_stage_stores_preview_and_pending_previews():
    """stage 存 preview；pending_previews 只读回读（回合级兜底网补卡的数据源）。"""
    wc.stage("thP", "submit_cost_sheet", {"sheet_id": 3}, {"动作": "提交成本表"})
    previews = wc.pending_previews("thP")
    assert previews.get("submit_cost_sheet", {}).get("动作") == "提交成本表"
    assert wc.pending_previews("thX") == {}


def test_import_confirm_momentum_rescued_to_preview():
    """抢跑自愈：陈述跑在闸前面时大脑带 confirm=true 首调 → 原地降级为预览+确认卡，
    绝不执行；用户消息之后 confirm=true 重调才落草稿（先看后落不因抢跑而绕过）。"""
    token = _set_ctx()
    try:
        att = {"attachment_id": "a1", "opportunity_id": "OPP-1",
               "uploader_user_id": "u-1", "original_filename": "成本.xlsx",
               "storage_key": "k1", "file_size": 10}
        feed_repo = _feed_repo_mock(get_attachment=att)
        flow_repo = MagicMock()
        flow_repo.save_cost_sheet_draft.return_value = {"id": 5, "name": "成本-成本"}
        flow_repo.get_cost_sheet.return_value = None
        flow_repo.close.return_value = None
        saved = {}
        storage = MagicMock()
        storage.read_bytes.return_value = b"xx"
        svc = MagicMock()
        svc.process_upload.return_value = {"status": "ok", "configs": {"CFG1": {}}}
        svc.close.return_value = None
        with patch("app.api.deps.ensure_opportunity_access",
                   return_value={"opportunity_id": "OPP-1", "customer_name": "华为"}), \
             patch("app.api.deps.user_has_permission", return_value=True), \
             patch("app.repository.feed_repo.FeedRepository", return_value=feed_repo), \
             patch("app.services.storage_adapter.get_storage", return_value=storage), \
             patch("app.services.quote_service.QuoteService", return_value=svc), \
             patch("app.api.portal._parse_result_to_cost_configs",
                   return_value=[{"name": "CFG1", "kp_rows": [], "l6_cost": 0}]), \
             patch("app.api.portal._attach_entity_card", return_value={"id": 1}), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo):
            first = sw.tool_import_cost_sheet({"attachment_id": "a1", "confirm": True})
            assert first.get("needs_confirmation") is True and not saved
            wc.note_user_message("th-1")
            out = sw.tool_import_cost_sheet({"attachment_id": "a1", "confirm": True})
        assert out["ok"] is True and out["sheet_id"] == 5
    finally:
        TOOL_CTX.reset(token)


# ── 重导护栏 / L6 配置级整价 / ask_user_card（2026-10-22 下午批次）──────────


def test_import_reimport_guard_blocks_overwriting_filled_draft():
    """重导护栏（死循环实锤）：已有草稿且有人工补价时，不带 sheet_id 的重导被拒，
    错误带现有 sheet_id 与 reset 指引；被拦时不应走到解析。"""
    token = _set_ctx()
    try:
        existing = {"sheet_id": 9, "name": "成本-WBB", "status": "draft",
                    "configs": [{"name": "CF1", "l6_cost": 12222, "kp_rows": [], "l6_rows": []}]}
        att = {"attachment_id": "ATT1", "original_filename": "成本-WBB.xlsx", "storage_key": "k"}
        with patch("app.api.deps.user_has_permission", return_value=True), \
             patch.object(dcore, "resolve_opportunity",
                          return_value={"ok": True, "opportunity_id": "OPP-1"}), \
             patch.object(dcore, "pick_attachment", return_value=(att, None)), \
             patch.object(dcore, "read_attachment_bytes", return_value=b"x"), \
             patch.object(dcore, "latest_cost_sheet", return_value=existing), \
             patch.object(dcore, "parse_cost_sheet",
                          side_effect=AssertionError("被护栏拦截时不应走到解析")):
            out = sw.tool_import_cost_sheet({"attachment_id": "ATT1", "customer_name": "客户"})
        assert out.get("status") == "reimport_guard" and out.get("sheet_id") == 9
        assert "reset" in out.get("error", "")
    finally:
        TOOL_CTX.reset(token)


def test_import_reimport_empty_draft_auto_inplace():
    """空草稿（无人工价）+ 不带 sheet_id 的重导 → 自动原地更新（staged sheet_id=现有
    草稿），不另起 -v2 挤掉探针在读的草稿。"""
    token = _set_ctx()
    try:
        wc._STORAGE = "memory"
        wc._MEM.clear()
        existing = {"sheet_id": 7, "name": "成本-X", "status": "draft",
                    "configs": [{"name": "CF1", "kp_rows": [], "l6_rows": []}]}
        att = {"attachment_id": "ATT2", "original_filename": "成本-X.xlsx", "storage_key": "k2"}
        with patch("app.api.deps.user_has_permission", return_value=True), \
             patch.object(dcore, "resolve_opportunity",
                          return_value={"ok": True, "opportunity_id": "OPP-1"}), \
             patch.object(dcore, "pick_attachment", return_value=(att, None)), \
             patch.object(dcore, "read_attachment_bytes", return_value=b"x"), \
             patch.object(dcore, "latest_cost_sheet", return_value=existing), \
             patch.object(dcore, "parse_cost_sheet",
                          return_value={"ok": True,
                                        "configs": [{"name": "CF1", "kp_rows": [], "l6_rows": []}],
                                        "digest": [{"name": "CF1"}]}):
            out = sw.tool_import_cost_sheet({"attachment_id": "ATT2", "customer_name": "客户"})
        assert out.get("needs_confirmation") is True  # 正常走预览，没撞护栏
        staged = wc.staged_args("th-1", "import_cost_sheet")
        assert staged and int(staged.get("sheet_id") or 0) == 7
    finally:
        TOOL_CTX.reset(token)
        wc._MEM.clear()


def test_set_cost_prices_l6_config_level():
    """L6 整机一口价（页面口径）：[{config_name, l6_price}] 写配置级 l6_cost，
    与 l6_rows 明细无关。"""
    token = _set_ctx()
    try:
        cfg = {"name": "CF1", "l6_cost": 0, "kp_rows": [], "l6_rows": []}
        sheet = {"id": 7, "name": "成本-X", "status": "draft", "configs": [cfg],
                 "bom_scheme_id": None, "quotation_id": ""}
        flow_repo = MagicMock()
        flow_repo.get_cost_sheet.return_value = sheet

        def _fake_save(opp_id, sid, name, configs, **kw):
            return {"id": sid or 7, "name": name}

        flow_repo.save_cost_sheet_draft.side_effect = _fake_save
        flow_repo.close.return_value = None
        with patch("app.api.deps.ensure_opportunity_access", return_value={}), \
             patch("app.repository.opportunity_repo.OpportunityRepository",
                   return_value=_FakeOppRepo([{"opportunity_id": "OPP-1", "customer_name": "华为"}])), \
             patch("app.repository.flow_repo.FlowRepository", return_value=flow_repo):
            out = sw.tool_set_cost_prices({"opportunity_id": "OPP-1", "sheet_id": 7,
                                           "prices": [{"config_name": "CF1", "l6_price": 12222}]})
        assert out["ok"] is True and cfg["l6_cost"] == 12222.0
        assert any("L6" in a for a in out["applied"])
    finally:
        TOOL_CTX.reset(token)


def test_ask_user_builds_and_validates():
    """向人提问（形状即类型）：options→choice（recommended 机械置首，多于一个拒绝）；
    fields→form；两种形状都不给=纯文本问，不立问题。"""
    token = _set_ctx()
    try:
        out = sw.tool_ask_user({
            "title": "匹配到 CPQ「广东御建」吗？",
            "options": [{"label": "否掉", "description": "保持未匹配"},
                        {"label": "确认匹配", "recommended": True}],
        })
        assert out["ok"] is True and out["await_user"] is True
        q = out["user_query"]
        assert q["kind"] == "choice"
        assert q["options"][0]["label"] == "确认匹配" and q["options"][0]["recommended"] is True
        out_f = sw.tool_ask_user({
            "title": "补价", "hint": "一个配置一个数",
            "fields": [{"key": "cf1_l6", "label": "CF1 的 L6 整机价", "type": "number"}]})
        assert out_f["ok"] is True and out_f["user_query"]["kind"] == "form"
        assert out_f["user_query"]["fields"][0]["key"] == "cf1_l6"
        # 形状错误 → 契约错误回大脑
        assert sw.tool_ask_user({"title": "x"})["ok"] is False  # 两种形状都不给
        assert sw.tool_ask_user({"title": "x", "options": [{"label": "A"}]})["ok"] is False  # 少于 2 个
        assert sw.tool_ask_user({"title": "x", "options": [
            {"label": "A", "recommended": True}, {"label": "B", "recommended": True}]})["ok"] is False
    finally:
        TOOL_CTX.reset(token)


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
