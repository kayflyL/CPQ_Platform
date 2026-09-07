# -*- coding: utf-8 -*-
"""配件选配冒烟回归：登记行在库内无精确对应时由唯一大脑在 kp_reason 节点回合
从引擎构建的每行候选池锁定真实料号。

select_kp_parts 是任务期工具（B2 接地）：取值域 = 引擎按「类目 × 机型系列适配」
构建的该行候选池，池外料号一律拒绝；选定按行键（类目|描述）持久化 ext.kp_picks，
客户改行自动失配作废。本文件只验证：任务期闸门、逐行接地校验、行键持久、
apply_kp_picks 落地、目标层「AI 反问」策略消费与大脑回合收敛语义；
不发起真实模型请求（run_stream_chat_loop 打桩）、不碰数据库。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 检索索引（服务端真相）：桶内同时按 part_id 与 name 小写登记（与 tool_search_kp_parts 同构）
_INDEX = {
    "cpu": {
        "101": {"part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0, "currency": "RMB"},
        "兆芯 kh-50000 32核": {"part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0, "currency": "RMB"},
        "102": {"part_id": "102", "name": "兆芯 KH-40000 16核", "price": 2800.0, "currency": "RMB"},
        "兆芯 kh-40000 16核": {"part_id": "102", "name": "兆芯 KH-40000 16核", "price": 2800.0, "currency": "RMB"},
    },
    "memory": {
        "201": {"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0, "currency": "RMB"},
        "三星 64gb ddr5 5600": {"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0, "currency": "RMB"},
    },
}


def _call_select(args: dict, *, task_active: bool = True, index=None, ext=None, saved=None, rows=None, ask_cats=None) -> dict:
    from app.services import skill_chat
    # ext/saved 都不复制：工具必须原地写引擎共享的同一对象（副本会丢落表，同 fill 的实测坑）
    if saved is None:
        saved = {}
    skill_chat._TOOL_CTX.set({
        "ext": ext if ext is not None else {}, "task_active": task_active,
        "kp_rows_ctx": rows if rows is not None else [
            {"row_key": "CPU|兆芯 50000 32核 处理器", "category": "CPU"},
            {"row_key": "Memory|DDR5 64G", "category": "Memory"},
        ],
        "kp_search_index": _INDEX if index is None else index,
        "kp_ask_cats": set(ask_cats or []),
        "save": lambda: saved.update(done=True),
    })
    return skill_chat.tool_select_kp_parts(args)


def test_select_kp_parts_blocked_before_task():
    """进任务前工具不可用：普通对话没有配件锁定权。"""
    res = _call_select({"picks": [{"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101",
                                   "reason": "r"}]}, task_active=False)
    assert res.get("ok") is False
    assert res.get("error") == "task_not_active"


def test_select_kp_parts_requires_unmatched_rows():
    res = _call_select({"picks": [{"row": "x", "reason": "r"}]}, index={}, rows=[])
    assert res.get("ok") is False
    assert res.get("error") == "no_unmatched_rows"


def test_select_kp_parts_requires_args():
    res = _call_select({})
    assert res.get("ok") is False
    assert res.get("error") == "invalid_args"


def test_select_kp_parts_locks_pool_members_in_batch():
    """批量：part_id 精确命中 / name 忽略大小写命中 → 行键持久化 ext.kp_picks 并 save。"""
    ext, saved = {}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "核数一致"},
        {"row": "Memory|DDR5 64G", "name": "三星 64GB DDR5 5600", "reason": "容量匹配"},
    ]}, ext=ext, saved=saved)
    assert res.get("ok") is True
    assert [r["ok"] for r in res["results"]] == [True, True]
    assert ext["kp_picks"]["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert ext["kp_picks"]["CPU|兆芯 50000 32核 处理器"]["price"] == 4500.0
    assert ext["kp_picks"]["Memory|DDR5 64G"]["part_id"] == "201"
    assert saved.get("done") is True


def test_select_kp_parts_partial_batch_and_out_of_pool():
    """池外料号拒绝并回显候选；同批合法行仍落定（部分成功不整批作废）。"""
    ext = {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "name": "Intel Xeon 8480", "reason": "r"},
        {"row": "Memory|DDR5 64G", "part_id": "201", "reason": "ok"},
        {"row": "不存在的行键", "part_id": "1", "reason": "r"},
    ]}, ext=ext)
    assert res.get("ok") is False          # 有失败行 → 整体 not ok（触发大脑重试）
    by_row = {r["row"]: r for r in res["results"]}
    assert by_row["CPU|兆芯 50000 32核 处理器"]["error"] == "not_in_search_results"
    assert "兆芯 KH-50000 32核" in by_row["CPU|兆芯 50000 32核 处理器"]["candidates"]
    assert by_row["不存在的行键"]["error"] == "row_not_found"
    assert by_row["Memory|DDR5 64G"]["ok"] is True
    assert list((ext.get("kp_picks") or {}).keys()) == ["Memory|DDR5 64G"]


def test_select_kp_parts_must_ask_records_recommendation():
    """AI 反问类目（must_ask）：select 不落地为锁定，登记为推荐（ext.kp_recommend）供确认卡标推荐。"""
    ext, saved = {}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "qty": 2, "reason": "核数一致"}]},
        ext=ext, saved=saved, ask_cats=["CPU"])
    assert res.get("ok") is True
    assert res["results"][0].get("ok") is True
    assert not (ext.get("kp_picks") or {}), "must_ask 类目不得落地为 kp_picks"
    rec = ext["kp_recommend"]["CPU|兆芯 50000 32核 处理器"]
    assert rec["name"] == "兆芯 KH-50000 32核"
    assert rec["qty"] == 2
    assert saved.get("done") is True


def test_select_kp_parts_non_ask_still_locks():
    """非反问类目照旧落地锁定（行为回归）。"""
    ext = {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "r"}]},
        ext=ext, ask_cats=["Memory"])
    assert res.get("ok") is True
    assert ext["kp_picks"]["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"


def test_kp_field_ask_policy_from_target_layer():
    """目标层「AI 反问」开关：kp_parts.ask=true → 大脑不代选（占位行交客户）；缺省 False。"""
    from app.services.skill_plan_runtime import _artifact_field_ask
    assert _artifact_field_ask({}, "kp_parts") is False
    on = {"target": {"artifacts": [{"fields": [
        {"key": "kp_parts", "label": "配件表", "ask": True}]}]}}
    assert _artifact_field_ask(on, "kp_parts") is True
    # 旧消费方不受泛化影响
    from app.services.skill_plan_runtime import _model_field_ask
    model_on = {"target": {"artifacts": [{"fields": [
        {"key": "server_model", "label": "服务器型号", "ask": True}]}]}}
    assert _model_field_ask(model_on) is True
    assert _model_field_ask(on) is False


def test_apply_kp_picks_replaces_placeholders():
    """占位行 + kp_picks → 真实料号行（数量保持、快照价格落行）；行键失配保持占位。"""
    from app.services.part_selector import apply_kp_picks, requirement_rows_to_parts
    kp_rows = [{"part_category": "CPU", "description": "兆芯 50000 32核 处理器", "qty": 2}]
    parts = requirement_rows_to_parts(kp_rows)
    assert parts[0]["unmatched"] is True
    picks = {"CPU|兆芯 50000 32核 处理器": {
        "part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0,
        "currency": "RMB", "reason": "核数一致"}}
    out, applied = apply_kp_picks(parts, picks)
    assert applied == 1
    row = out[0]
    assert row["unmatched"] is False
    assert row["pn"] == "兆芯 KH-50000 32核"
    assert row["unit_price"] == 4500.0
    assert row["qty"] == 2
    assert "核数一致" in row["grounded_spec"]
    # 客户改过描述 → 行键失配，pick 自动作废，保持占位白盒
    out2, applied2 = apply_kp_picks(parts, {"CPU|客户改口后的描述": picks[
        "CPU|兆芯 50000 32核 处理器"]})
    assert applied2 == 0
    assert out2[0]["unmatched"] is True


def _seed_index():
    """直接种子检索索引（DB 无关）：brain fake_loop 里 search→select 的 search 替身。"""
    from app.services import skill_chat
    ctx = skill_chat._TOOL_CTX.get()
    entry = {"part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0, "currency": "RMB"}
    ctx["kp_search_index"] = {"cpu": {"101": entry, "兆芯 kh-50000 32核": entry}}


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_kp_brain_records_picks_in_ext():
    """大脑回合经工具落定：picks 写进引擎当前 ext（跨轮持久），narration 留痕。"""
    from unittest.mock import patch
    from app.services import skill_chat

    async def fake_loop(msg, **kwargs):
        _seed_index()
        res = skill_chat.tool_select_kp_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "核数一致"}]})
        return {"tool_calls_log": [{"name": "select_kp_parts", "result": res}]}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "kp_parts": [{"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2, "unmatched": True}]}
    skill_chat._TOOL_CTX.set({"ext": engine_ctx["ext"], "save": lambda: None})
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    assert engine_ctx["ext"]["kp_picks"]["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert "kp_narration" in engine_ctx


def test_kp_brain_respects_declined_pick():
    """空手而归（散文无工具调用）→ 尊重交回，不纠偏不重试。

    2026-09-07 唯一大脑薄守卫语义：强纠偏（「必须二选一」系统提醒/散文二次纠偏）
    已随三工厂合并删除——大脑交回什么引擎接什么。空 KP 卡的防线改为两道确定性
    闸门：kp 硬门（unmatched>0 必弹确认卡，引擎不 done）+ 交表前终检轮。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}
    msgs = []

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        msgs.append(msg)
        return {"answer": "请回复确认内存组合方式？", "tool_calls_log": []}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "kp_parts": [{"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2, "unmatched": True}]}
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    assert "kp_picks" not in engine_ctx["ext"]
    assert calls["n"] == 1                      # 无工具被拒 → 一轮即收敛，不再逼问
    assert len(msgs) == 1


def test_kp_brain_abandons_silent_round():
    """answer 空手（思考截断/断流降级：零工具零正文）→ 不纠偏直接弃权，交引擎硬门征询。

    纠偏重跑对截断空手是原样复现（2026-09-06 实测 31s 烧 10 轮调用零产出），
    弃权后未选定行由硬门征询卡接管，墙钟有界。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        return {"tool_calls_log": []}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "kp_parts": [{"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2, "unmatched": True}]}
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    assert "kp_picks" not in engine_ctx["ext"]
    assert calls["n"] == 1


def test_kp_brain_retries_rejected_rows_then_gives_up():
    """调了工具但有行被池校验拒绝 → 喂回真实返回重试（≤3 次），失败的行不落定。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        _seed_index()
        res = skill_chat.tool_select_kp_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "name": "Not-In-Pool", "reason": "r"}]})
        return {"tool_calls_log": [{"name": "select_kp_parts", "result": res}]}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "kp_parts": [{"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2, "unmatched": True}]}
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    assert calls["n"] == 3
    assert "kp_picks" not in engine_ctx["ext"]


def test_kp_brain_rebinds_ext_after_phase_copy():
    """阶段函数的复制重赋不得丢选定：brain 回合必须把 _TOOL_CTX["ext"] 重绑到引擎
    当前对象，否则 select_kp_parts 写进被弃用的旧副本（同 model 回合实测坑）。"""
    from unittest.mock import patch
    from app.services import skill_chat

    async def fake_loop(msg, **kwargs):
        _seed_index()
        res = skill_chat.tool_select_kp_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "r"}]})
        return {"tool_calls_log": [{"name": "select_kp_parts", "result": res}]}

    stale = {"server_type": "通用计算服务器"}
    current = dict(stale)
    engine_ctx = {"ext": current, "kp_parts": [{"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2, "unmatched": True}]}
    skill_chat._TOOL_CTX.set({"ext": stale, "save": lambda: None})
    brain = skill_chat.make_agent_brain(persona="测试角色")
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    assert "kp_picks" in current, "工具落定必须写进引擎当前 ext，而非旧副本"
    assert "kp_picks" not in stale


# ── 2026-09-05 大脑提问卡（ask_user）+ 已锁定行上下文 ─────────────────────

def _call_ask(args: dict, *, task_active: bool = True, asks=None) -> dict:
    from app.services import skill_chat
    if asks is None:
        asks = []
    skill_chat._TOOL_CTX.set({"ext": {}, "task_active": task_active, "brain_asks": asks})
    return skill_chat.tool_ask_user(args)


def test_ask_user_blocked_before_task():
    res = _call_ask({"question": "q", "options": [{"label": "a"}]}, task_active=False)
    assert res.get("ok") is False and res.get("error") == "task_not_active"


def test_ask_user_registers_structured_question():
    asks: list = []
    res = _call_ask({"question": "1.92T 用哪种接口？",
                     "options": [{"label": "SATA"}, {"label": "NVMe", "description": "更快"}],
                     "row": "HDD/SSD|1.92T"}, asks=asks)
    assert res.get("ok") is True and len(asks) == 1
    ask = asks[0]
    assert ask["row"] == "HDD/SSD|1.92T"
    assert [o["label"] for o in ask["options"]] == ["SATA", "NVMe"]


def test_ask_user_one_card_per_turn():
    """一回合一卡（与缺口卡单焦点序列同口径）：已有待答问题再调即拒绝。"""
    asks = [{"question": "先答这个", "options": [{"label": "x"}], "row": ""}]
    res = _call_ask({"question": "又来", "options": [{"label": "y"}]}, asks=asks)
    assert res.get("ok") is False and res.get("error") == "one_ask_per_turn"
    assert len(asks) == 1


def test_ask_user_rejects_invalid_shapes():
    assert _call_ask({"options": [{"label": "a"}]}).get("error") == "invalid_args"
    assert _call_ask({"question": "q", "options": []}).get("error") == "invalid_args"
    assert _call_ask({"question": "q", "options": [{"desc": "无label"}]}).get("error") == "invalid_args"


def test_kp_brain_collects_asks_and_locked_rows_view():
    """kp 大脑回合：ask_user 登记的问题回传 engine_ctx.kp_asks；已锁定行以
    类目/描述/数量/已选名称进提示词上下文（候选池看不见已锁定行的幻觉根治）。"""
    from unittest.mock import patch
    from app.services import skill_chat

    async def fake_loop(msg, **kwargs):
        captured["sys_prompt"] = kwargs.get("system_prompt") or ""
        captured["context_block"] = kwargs.get("context_block") or ""
        captured["user_msg"] = msg
        captured["allowed_tool_ids"] = kwargs.get("allowed_tool_ids") or []
        _seed_index()
        skill_chat.tool_ask_user({"question": "1.92T 用哪种接口？",
                                  "options": [{"label": "SATA"}, {"label": "NVMe"}],
                                  "row": "HDD/SSD|1.92T"})
        res = skill_chat.tool_select_kp_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "r"}]})
        return {"tool_calls_log": [
            {"name": "ask_user", "result": {"ok": True}},
            {"name": "select_kp_parts", "result": res}]}

    captured: dict = {}

    engine_ctx = {
        "ext": {},
        "kp_parts": [
            {"category": "Memory", "request_spec": "DDR5 64G", "qty": 8,
             "name": "三星 64GB DDR5 5600", "unmatched": False},
            {"category": "HDD/SSD", "request_spec": "1.92T", "qty": 1, "unmatched": True},
            {"category": "CPU", "request_spec": "兆芯 50000 32核 处理器", "qty": 2,
             "unmatched": True},
        ],
    }
    brain = skill_chat.make_agent_brain(persona="测试角色")
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("kp_reason", {}, engine_ctx))
    asks = engine_ctx.get("kp_asks") or []
    assert len(asks) == 1 and asks[0]["row"] == "HDD/SSD|1.92T"
    # 已锁定行以类目/描述/数量/已选名称进大脑 user 消息（节点输入数据视图），
    # 且不带库内编码（part_id）——2026-09-07 起节点动态数据统一走 user_msg 的
    # 「本节点输入数据」JSON，context_block 只留登记表+跨回合工作记忆
    user_view = captured.get("user_msg") or ""
    assert "已锁定的部件行" in user_view
    assert "三星 64GB DDR5 5600" in user_view
    assert '"selected"' in user_view
    assert "101" not in user_view.split("已锁定的部件行")[1].split("待选型行清单")[0]
    assert "待选型行清单" in user_view
    # system 静态化：动态数据不进 system；工具可用性走机制层（allowed_tool_ids），
    # 不再要求 system 文本复述工具契约（契约在工具 schema/抽屉，2026-09-07 起）
    assert "已锁定的部件行" not in (captured.get("sys_prompt") or "")
    assert "ask_user" in (captured.get("allowed_tool_ids") or [])


def test_kp_row_merge_signal_updates_row_description():
    """行绑定的提问卡点击直传：答案合入该行描述 → 行键失配 → 旧 pick 作废。"""
    from app.services.slot_contract import apply_structured_slots
    ext = {"kp_rows": [{"part_category": "HDD/SSD", "description": "1.92T", "qty": 1}],
           "kp_picks": {"HDD/SSD|1.92T": {"name": "旧选件", "price": 1}}}
    notes = apply_structured_slots(
        ext, {"kp_row_merge": {"row": "HDD/SSD|1.92T", "answer": "SATA 接口"}}, "")
    assert notes and "1.92T SATA 接口" in notes[0]
    assert ext["kp_rows"][0]["description"] == "1.92T SATA 接口"
    # 旧 pick 键已失配（不改数据，靠键不等自然作废）
    assert "HDD/SSD|1.92T SATA 接口" not in ext["kp_picks"]
    # 行键不存在 → 静默无操作
    notes2 = apply_structured_slots(
        ext, {"kp_row_merge": {"row": "不存在的行", "answer": "x"}}, "")
    assert not [n for n in notes2 if "更新" in n]
