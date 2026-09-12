# -*- coding: utf-8 -*-
"""行清单增量收敛（2026-09-11：P2 去重 → P3 身份铸造）：身份唯一 + 已了结可见 + 引用只认身份。

实测病象（模糊场景 before 基线：14 轮 / 13 张卡 / repeat_cats=5）：大脑每轮手拼
「类目|描述」，措辞一漂行键就变 → 同一需求长成两行（配件表 11 行里有 2 行 RAID 卡、
2 行系统盘），并把同一件事反复问客户。本文件的断言就是这套收敛机制的报警器：
1. 行身份由**来源**铸造（reg:/cfg:/pick:/row: 锚点），描述改写不换身份、行数不随轮次增长；
2. 行引用只认两档——清单内 row_id 原文 → 清单内 row_key 原文；措辞漂移一律 row_unknown，
   引擎不再按文本相似度「认领」一行（P3-3：拒绝机械正则，不铸同义新行）；
3. 已了结行必须随行清单下发（大脑看得见自己处理过哪几行），且拒收重复确认（除非 reopen）；
4. pick 按行身份落键、条目自带 rev；内容版本变了 → stale → 重选，行数不变；
5. 同类目多行是合法需求：描述确实不同就各留一行，引擎不做词元/包含归并；
6. row_desc_norm 只吸收排版/数量词噪声（供 rev 判定与旧数据兼容），不吸收规格词。
"""
import asyncio
import re

from app.services import skill_tool_context

_ROWS = [
    {"row_id": "kp-1", "row_key": "HDD/SSD|系统盘 2块480G SSD", "category": "HDD/SSD",
     "description": "系统盘 2块480G SSD", "qty": 2, "status": "已锁定",
     "part": "480G SATA SSD 企业级 ×2", "settled": True},
    {"row_id": "kp-2", "row_key": "Raid card|RAID卡 8口4G缓存", "category": "Raid card",
     "description": "RAID卡 8口4G缓存", "qty": 1, "status": "待处理",
     "part": "", "settled": False},
]


# ── 1. 归一化只吃排版/数量词 ──────────────────────────────────────────────

def test_row_desc_norm_folds_layout_noise_only():
    from app.services.part_selector import row_desc_norm
    a = row_desc_norm("系统盘 2块480G SSD")
    assert a == row_desc_norm("系统盘 480G SSD ×2")
    assert a == row_desc_norm("系统盘480G SSD")
    assert row_desc_norm("RAID卡 8口4G缓存") == row_desc_norm("RAID卡 8口 4G缓存")
    # 规格词/量纲词不进噪声表：同类目多行（千兆 vs 万兆、8口 vs 16口）仍必须是两行
    assert row_desc_norm("4个千兆网口") != row_desc_norm("2个万兆网口")
    assert row_desc_norm("RAID卡 8口") != row_desc_norm("RAID卡 16口")
    assert row_desc_norm("12*3.5 SATA") == "12*3.5sata", "12*3.5 的 * 不是数量词"

# ── 2. 行引用两档解析：只认身份，不猜文本（P3-3）────────────────────────

def test_resolve_row_ref_only_identity_and_settled_passthrough():
    """引用只认两档：清单内 row_id 原文 → 清单内 row_key 原文（等价别名）。"""
    from app.services.part_selector import resolve_row_ref
    assert resolve_row_ref("kp-1", _ROWS)["why"] == "row_id"
    assert resolve_row_ref("Raid card|RAID卡 8口4G缓存", _ROWS)["row_id"] == "kp-2"
    hit = resolve_row_ref("kp-1", _ROWS)
    assert hit["row"] == "HDD/SSD|系统盘 2块480G SSD"
    assert hit["settled"] is True and hit["status"] == "已锁定"
    assert hit["part"].startswith("480G SATA SSD")


def test_resolve_row_ref_rejects_drifted_wording_instead_of_guessing():
    """措辞漂移不再是引用（P3-3 删掉归一化猜测档）：一律 row_unknown + 可用 row_id 清单。"""
    from app.services.part_selector import resolve_row_ref
    for drifted in ("系统盘480G SSD ×2", "HDD/SSD|系统盘 480G SSD", "系统盘 480G SSD"):
        miss = resolve_row_ref(drifted, _ROWS)
        assert miss["error"] == "row_unknown", drifted
        assert [c["row_id"] for c in miss["candidates"]] == ["kp-1", "kp-2"], drifted


def test_resolve_row_ref_unknown_returns_available_row_ids():
    from app.services.part_selector import resolve_row_ref
    bad = resolve_row_ref("GPU|H100", _ROWS)
    assert bad["error"] == "row_unknown"
    assert [c["row_id"] for c in bad["candidates"]] == ["kp-1", "kp-2"]
    assert not resolve_row_ref("", _ROWS)["candidates"], "空引用没有候选"


# ── 3. ask_user：行引用收口 + 已了结闸门 ──────────────────────────────────

def _ask(args, *, rows=None, asks=None, task_active=True):
    from app.services import skill_tools_misc
    asks = [] if asks is None else asks
    ctx = {"ext": {}, "task_active": task_active, "brain_asks": asks}
    if rows is not None:
        ctx["kp_rows_all"] = rows
    skill_tool_context.TOOL_CTX.set(ctx)
    return skill_tools_misc.tool_ask_user(args), asks


def test_ask_user_rejects_row_outside_the_list():
    res, asks = _ask({"question": "系统盘怎么配？", "options": [{"label": "企业级"}],
                      "row": "HDD/SSD|系统盘 960G SSD"}, rows=_ROWS)
    assert res.get("ok") is False and res.get("error") == "row_unknown"
    assert [r["row_id"] for r in res["rows"]] == ["kp-1", "kp-2"]
    assert not asks, "拒收的行不得留下待答问题"

def test_ask_user_blocks_settled_row_unless_reopen():
    """已了结行拒收（除非显式 reopen）；卡片按 row_id 绑行（P3-3）。"""
    res, asks = _ask({"question": "系统盘再确认一下？", "options": [{"label": "企业级"}],
                      "row": "kp-1"}, rows=_ROWS)
    assert res.get("ok") is False and res.get("error") == "row_already_settled"
    assert res.get("row") == "HDD/SSD|系统盘 2块480G SSD"
    assert res.get("part").startswith("480G SATA SSD")
    assert not asks
    ok, asks2 = _ask({"question": "系统盘要改成 960G 吗？", "options": [{"label": "960G"}],
                      "row": "kp-1", "reopen": True}, rows=_ROWS)
    assert ok.get("ok") is True and asks2[0]["row"] == "kp-1", "卡片绑身份，不绑措辞"


def test_ask_user_rejects_drifted_wording_instead_of_guessing():
    res, asks = _ask({"question": "RAID 卡选哪档？", "options": [{"label": "8口 4G"}],
                      "row": "Raid card|RAID卡 8口 4G 缓存 ×1"}, rows=_ROWS)
    assert res.get("ok") is False and res.get("error") == "row_unknown"
    assert [r["row_id"] for r in res["rows"]] == ["kp-1", "kp-2"]
    assert not asks
    ok, asks2 = _ask({"question": "RAID 卡选哪档？", "options": [{"label": "8口 4G"}],
                      "row": "kp-2"}, rows=_ROWS)
    assert ok.get("ok") is True and asks2[0]["row"] == "kp-2"


def test_ask_user_without_row_list_stays_back_compatible():
    """非 kp 节点（没有行清单）里 ask_user 是登记表字段确认卡，不该被行校验拦住。"""
    res, asks = _ask({"question": "平台确认？", "options": [{"label": "Polaris"}],
                      "row": "whatever|行", "slot": "platform_type"})
    assert res.get("ok") is True and asks[0]["row"] == "whatever|行"


# ── 4. 已了结行随行清单下发 ──────────────────────────────────────────────

def test_bridge_ctx_publishes_settled_rows_with_status():
    from app.services.skill_node_plugins import plugin_for
    from app.services.skill_node_state import kp_state, KP_PICKS
    engine = {
        "ext": {"kp_rows": [{"part_category": "HDD/SSD", "description": "系统盘", "qty": 2}]},
        "kp_parts": [
            {"category": "HDD/SSD", "request_spec": "系统盘", "qty": 2, "unmatched": True},
            {"category": "CPU", "request_spec": "AMD平台", "qty": 2, "unmatched": False,
             "name": "AMD 9654"},
        ],
        "flow_configs": {}, "node_state": {},
    }
    kp_state(engine)[KP_PICKS] = {"HDD/SSD|系统盘": {"name": "480G SATA SSD 企业级 ×2"}}
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    all_rows = {r["row_key"]: r for r in ctx["kp_rows_all"]}
    assert all_rows["HDD/SSD|系统盘"]["status"] == "已锁定"
    assert all_rows["HDD/SSD|系统盘"]["part"].startswith("480G SATA SSD")
    assert all_rows["HDD/SSD|系统盘"]["settled"] is True
    assert all_rows["CPU|AMD平台"]["settled"] is True, "已落地的行也算已了结"
    assert all_rows["CPU|AMD平台"]["part"] == "AMD 9654"
    assert [r["row_key"] for r in ctx["kp_rows_ctx"]] == ["HDD/SSD|系统盘"], (
        "待选型清单仍只放未落地行，已落地行只进全量表"
    )


# ── 5. 归一化去重 + pick 归一化落地 ───────────────────────────────────────

def _run_phase(ctx: dict) -> dict:
    from app.services.skill_phases import phase_kp_reason
    asyncio.run(phase_kp_reason(ctx, {}, None))
    return ctx

def test_phase_kp_reason_row_identity_is_stable_across_turns():
    """同一份输入连跑两轮：行身份与行数都不变。

    旧实现 row_id = 哈希(类目|描述)，措辞一漂就换 id → 同一需求长成两行；P3-1 起身份由
    来源铸造（reg:/cfg:），P3-3 起引擎不再按文本相似度「认领」行——要合成一行必须显式
    引用既有 row_id（见 select_parts 用例）。

    归属收口（2026-09-12）：声明行（cfg:）按定义只承载「客户原话未覆盖、AI 判断要配」的
    类目；已被线索登记表申报的类目（有部件槽的 CPU/HDD/SSD/…）属主是 agent_fill，登记表
    就是这条需求的行，kp_reason 再声明一行 = 同一需求两条身份 → 客户后补型号时新旧并存。
    """

    def _run_once():
        ctx = {
            "ext": {"kp_rows": [{"part_category": "HDD/SSD",
                                  "description": "系统盘 2块480G SSD", "qty": 2}]},
            "node_state": {"kp_reason": {"config": [
                {"category": "HDD/SSD", "spec": "系统盘 480G SSD ×2", "qty": 2}]}},
            "baselines": [{"server_type_name": "通用计算服务器", "series": "Polaris"}],
        }
        _run_phase(ctx)
        return [(str(p.get("origin") or ""), str(p.get("row_id") or ""))
                for p in ctx["kp_parts"]]

    first = _run_once()
    assert first == _run_once(), "同一来源 = 同一身份：行数不随轮次增长"
    assert [o for o, _ in first] == ["reg:HDD/SSD"], (
        "登记表已申报的类目不再声明 cfg: 行：同一需求只有一条身份，客户后补型号不会新旧两行并存")
    # 登记表没有的大类（Bridge/HBA/NVSwitch）才是声明行的本意：仍按来源铸 cfg: 身份
    ctx2 = {
        "ext": {},
        "node_state": {"kp_reason": {"config": [{"category": "HBA", "spec": "HBA 卡 8Gb 双口"}]}},
        "baselines": [{"server_type_name": "通用计算服务器", "series": "Polaris"}],
    }
    _run_phase(ctx2)
    assert [str(p.get("origin") or "") for p in ctx2["kp_parts"]] == ["cfg:HBA"], (
        "登记表没有的大类（Bridge/HBA/NVSwitch）仍可由 kp_reason 声明")


def test_phase_kp_reason_applies_drifted_pick_to_registered_row():
    """pick 的行键措辞漂了也要落到那一行——不补占位、不留下第二行。"""
    ctx = {
        "ext": {"kp_rows": [{"part_category": "HDD/SSD",
                              "description": "系统盘 2块480G SSD", "qty": 2}]},
        "node_state": {"kp_reason": {"picks": {
            "HDD/SSD|系统盘480G SSD×2": {"name": "480G SATA SSD 企业级 ×2",
                                          "price": 1200.0, "currency": "RMB"}}}},
        "baselines": [{"server_type_name": "通用计算服务器", "series": "Polaris"}],
    }
    _run_phase(ctx)
    parts = ctx["kp_parts"]
    assert len(parts) == 1, [p.get("request_spec") for p in parts]
    assert parts[0]["name"] == "480G SATA SSD 企业级 ×2"
    assert parts[0]["unmatched"] is False, "漂移的行键不许再留一行未落地"
    assert ctx["kp_summary"]["unmatched_count"] == 0


def test_legit_multi_row_category_survives_dedupe():
    """同类目多行是合法需求：描述确实不同就不许合并。"""
    ctx = {
        "ext": {"kp_rows": [
            {"part_category": "NIC", "description": "4个千兆网口", "qty": 1},
            {"part_category": "NIC", "description": "2个万兆网口", "qty": 1}]},
        "node_state": {"kp_reason": {}},
        "baselines": [{"server_type_name": "通用计算服务器", "series": "Polaris"}],
    }
    _run_phase(ctx)
    assert len(ctx["kp_parts"]) == 2



def test_select_parts_rejects_drifted_row_ref_without_declaring_a_row():
    """措辞漂移的 row 引用不再被「认领」到既有行（P3-3）：回 row_unknown + row_id 清单。

    也绝不静默铸新行——那正是同一需求长出两行、被问三遍的根；要新增同类目第二行必须显式
    new_row=true 并写清 category/spec。
    """
    from app.services import data_tools, skill_tools_select

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        rows = [{"part_id": "301", "name": "480G SATA SSD 企业级", "category": "HDD/SSD",
                 "price": 1200.0, "currency": "RMB"}]
        want = re.sub(r"\s+", "", str(name or "")).lower()
        hit = [r for r in rows if str(r.get("category")) == str(category)
               and re.sub(r"\s+", "", r["name"]).lower() == want]
        return {"ok": True, "category": category, "source": "kp_library/name_lookup",
                "rows": hit, "total": len(hit)}

    engine: dict = {"node_state": {}}
    rows = [{"row_key": "HDD/SSD|系统盘 2块480G SSD", "row_id": "kp-1",
             "category": "HDD/SSD", "description": "系统盘 2块480G SSD",
             "qty": 2, "specified": True}]
    skill_tool_context.TOOL_CTX.set({
        "ext": {}, "task_active": True, "engine": engine, "kp_rows_ctx": rows,
        "save": lambda: None,
    })
    orig = data_tools.lookup_parts_by_name
    data_tools.lookup_parts_by_name = _by_name
    try:
        res = skill_tools_select.tool_select_parts({"picks": [
            {"row": "HDD/SSD|系统盘480G SSD ×2", "name": "480G SATA SSD 企业级",
             "reason": "漂移行键"}]})
    finally:
        data_tools.lookup_parts_by_name = orig
    assert res.get("ok") is False, res
    r0 = res["results"][0]
    assert r0["error"] == "row_unknown", r0
    assert [x["row_id"] for x in r0["rows"]] == ["kp-1"], "回可用 row_id，逼大脑用清单原文"
    kp = (engine.get("node_state") or {}).get("kp_reason") or {}
    assert not kp.get("config"), "漂移行键不得新声明一行"
    assert not kp.get("picks"), "解析不到行就不落 pick"

    # 用清单原文 row_id 引用 → 落键按行身份（P3-2）
    data_tools.lookup_parts_by_name = _by_name
    try:
        res2 = skill_tools_select.tool_select_parts({"picks": [
            {"row": "kp-1", "name": "480G SATA SSD 企业级", "reason": "身份引用"}]})
    finally:
        data_tools.lookup_parts_by_name = orig
    assert res2.get("ok") is True, res2
    picks = ((engine.get("node_state") or {}).get("kp_reason") or {}).get("picks") or {}
    assert list(picks) == ["kp-1"], picks
    assert picks["kp-1"]["category"] == "HDD/SSD", "条目自带身份字段，落行不必再反解键文本"
