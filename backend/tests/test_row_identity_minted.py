# -*- coding: utf-8 -*-
"""P3-1 行身份铸造（2026-09-11）：身份由**来源**决定，不由**文本**决定。

旧实现 row_id = sha1(类目|描述)，描述改一个字就换 id、旧 pick 失配 → 同一需求长出两行。
本文件锁定新契约：
- 同一 origin 描述改写 N 次 → row_id 恒定（内容版本 rev 只随**实质内容**变）；
- 登记行（reg:）与声明行（cfg:）都能铸造；
- 同类目多行 → 序号锚点，各自稳定且互不相同；
- 引擎从不按文本相似度猜同一行（两行同描述、无 origin → 两个不同 id）；
- pick 补行与 apply_kp_picks 都不丢身份。
"""
import re

from app.services.part_selector import (
    apply_kp_picks, config_rows_to_parts, ensure_pick_rows, requirement_rows_to_parts,
    row_content_rev, row_id_for_origin, row_origin, stamp_row_identity)


# ── 1. 铸造器本身 ──────────────────────────────────────────────────────

def test_origin_shape_and_id_determinism():
    assert row_origin("reg", "Memory") == "reg:Memory"
    assert row_origin("reg", "NIC", 2, 3) == "reg:NIC#2"
    assert row_origin("reg", "", 1, 1) == ""
    a = row_id_for_origin("reg:Memory")
    assert a.startswith("kp-") and len(a) == 11
    assert a == row_id_for_origin("reg:Memory"), "同一来源必须铸出同一个 id"
    assert row_id_for_origin("") == ""
    assert row_id_for_origin("reg:Memory") != row_id_for_origin("cfg:Memory"), (
        "不同来源（登记 vs 声明）是不同身份"
    )


# ── 2. 登记行：身份不随描述改写而变，内容版本只随实质内容变 ──────────────

def test_registration_row_id_is_stable_across_description_rewrites():
    out = []
    for desc in ["系统盘 2块480G SSD", "系统盘 480G SSD ×2", "系统盘480G SSD"]:
        out.append(requirement_rows_to_parts(
            [{"part_category": "HDD/SSD", "description": desc, "qty": 2}])[0])
    assert {r["origin"] for r in out} == {"reg:HDD/SSD"}
    assert len({r["row_id"] for r in out}) == 1, "同一来源的行身份不得随描述改写而变"
    assert len({r["rev"] for r in out}) == 1, "只差排版/数量词 = 同一内容，rev 不变"


def test_material_content_change_keeps_id_but_bumps_rev():
    a = requirement_rows_to_parts([{"part_category": "HDD/SSD", "description": "系统盘 480G SSD"}])[0]
    b = requirement_rows_to_parts([{"part_category": "HDD/SSD", "description": "系统盘 960G SSD"}])[0]
    assert a["row_id"] == b["row_id"], "实质改配置仍是同一行（由客户改口触发重选，不是新铸一行）"
    assert a["rev"] != b["rev"], "实质内容变了，内容版本必须变"
    assert row_content_rev("HDD/SSD", "") == row_content_rev("HDD/SSD", "HDD/SSD")


# ── 3. 声明行（cfg）同样铸造；同类目多行 → 序号锚点 ─────────────────────

def test_config_rows_minted_with_cfg_origin_and_ordinals():
    rows = config_rows_to_parts([{"category": "NIC", "spec": "2个万兆网口"},
                                 {"category": "NIC", "spec": "4个千兆网口"}])
    assert [r["origin"] for r in rows] == ["cfg:NIC#1", "cfg:NIC#2"]
    assert rows[0]["row_id"] != rows[1]["row_id"], "同类目两行是两个身份"


def test_multi_row_ordinal_survives_description_rewrite():
    def ids(specs):
        return [r["row_id"] for r in config_rows_to_parts(
            [{"category": "NIC", "spec": s} for s in specs])]
    a = ids(["2个万兆网口", "4个千兆网口"])
    b = ids(["2个万兆网口（双口）", "4个千兆网口"])
    assert a[1] == b[1], "第二行没动，身份不得变"
    assert a[0] != a[1]


# ── 4. 盖章：幂等，且绝不按文本并行的“猜” ───────────────────────────────

def test_stamp_is_idempotent_and_never_merges_by_text():
    parts = [{"category": "CPU", "request_spec": "同"}, {"category": "CPU", "request_spec": "同"}]
    stamp_row_identity(parts, kind="row")
    assert [p["origin"] for p in parts] == ["row:CPU#1", "row:CPU#2"]
    assert parts[0]["row_id"] != parts[1]["row_id"], "两行同描述也不许按文本并成一行"
    before = [(p["origin"], p["row_id"], p["rev"]) for p in parts]
    stamp_row_identity(parts, kind="row")
    assert [(p["origin"], p["row_id"], p["rev"]) for p in parts] == before, "已有身份不得重铸"


# ── 5. pick 补行与落地都不丢身份 ──────────────────────────────────────

def test_pick_placeholder_and_apply_preserve_identity():
    parts = ensure_pick_rows([], {"Memory|512G": {"name": "64G RDIMM"}})
    assert parts[0]["origin"] == "pick:Memory"
    out, applied = apply_kp_picks(parts, {"Memory|512G": {"name": "64G RDIMM", "price": 1}})
    assert applied == 1
    assert out[0]["origin"] == "pick:Memory"
    assert out[0]["row_id"] == parts[0]["row_id"], "落地换的是内容，不是身份"


# ── 6. 行清单发布带铸造 id，且台账跨轮不换 id、只更新 rev ────────────────

def test_bridge_ctx_publishes_minted_row_id_and_ledger():
    from app.services.skill_node_plugins import plugin_for
    from app.services.skill_node_state import KP_ROW_IDS, kp_state
    reg = [{"part_category": "HDD/SSD", "description": "系统盘 480G SSD", "qty": 2}]
    engine = {"ext": {"kp_rows": reg}, "kp_parts": requirement_rows_to_parts(reg),
              "flow_configs": {}, "node_state": {}}
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    row = ctx["kp_rows_all"][0]
    assert row["origin"] == "reg:HDD/SSD"
    assert row["row_id"] == row_id_for_origin("reg:HDD/SSD")
    ledger = kp_state(engine)[KP_ROW_IDS]
    assert ledger["reg:HDD/SSD"]["row_id"] == row["row_id"]

    reg2 = [{"part_category": "HDD/SSD", "description": "系统盘 960G SSD", "qty": 2}]
    engine["ext"] = {"kp_rows": reg2}
    engine["kp_parts"] = requirement_rows_to_parts(reg2)
    ctx2: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx2)
    assert ctx2["kp_rows_all"][0]["row_id"] == row["row_id"], "描述改写不得换身份"
    assert kp_state(engine)[KP_ROW_IDS]["reg:HDD/SSD"]["rev"] != row["rev"], "内容改了 rev 要更新"


# ── 7. P3-2：pick 按行身份落键 + 内容版本失配要重选 ─────────────────────

def _row(cat, desc, rid, origin, rev=None):
    from app.services.part_selector import row_content_rev
    return {"category": cat, "request_spec": desc, "description": desc,
            "row_id": rid, "origin": origin,
            "rev": rev if rev is not None else row_content_rev(cat, desc),
            "qty": 1, "unmatched": True}


def test_pick_key_and_entry_carry_row_identity():
    from app.services.part_selector import pick_entry_identity, pick_key_for_row
    r = _row("Memory", "内存 512G DDR5", "kp-aaaa1111", "reg:Memory")
    assert pick_key_for_row(r) == "kp-aaaa1111"
    ent = pick_entry_identity(r)
    assert ent["row_id"] == "kp-aaaa1111" and ent["origin"] == "reg:Memory"
    assert ent["category"] == "Memory" and ent["description"] == "内存 512G DDR5"
    assert ent["rev"] == r["rev"]


def test_stale_pick_is_not_applied_so_row_re_selects():
    from app.services.part_selector import apply_kp_picks, pick_is_stale
    r = _row("Memory", "内存 512G DDR5", "kp-aaaa1111", "reg:Memory")
    entry = {"row_id": "kp-aaaa1111", "origin": "reg:Memory", "category": "Memory",
             "description": "内存 512G DDR5", "rev": r["rev"], "name": "64G RDIMM", "price": 1}
    assert pick_is_stale(entry, "Memory", "内存 512G DDR5") is False
    # 客户改口成 1T → 同一行身份不变，但内容版本变了 → 旧 pick 失效、须重选
    r2 = _row("Memory", "内存 1T DDR5", "kp-aaaa1111", "reg:Memory")
    assert pick_is_stale(entry, "Memory", "内存 1T DDR5") is True
    out, applied = apply_kp_picks([r2], {"kp-aaaa1111": entry})
    assert applied == 0 and out[0]["unmatched"] is True, "内容改了，不许拿旧 pick 落行"


def test_layout_noise_rewrite_keeps_pick_valid():
    from app.services.part_selector import apply_kp_picks, pick_is_stale
    r = _row("HDD/SSD", "系统盘 480G SSD", "kp-bbbb2222", "reg:HDD/SSD")
    entry = {"row_id": "kp-bbbb2222", "category": "HDD/SSD", "description": "系统盘 480G SSD",
             "rev": r["rev"], "name": "480G SATA SSD 企业级", "price": 1200}
    r2 = _row("HDD/SSD", "系统盘 2块480G SSD", "kp-bbbb2222", "reg:HDD/SSD")
    assert pick_is_stale(entry, "HDD/SSD", "系统盘 2块480G SSD") is False, "只差排版/数量词 = 同一内容"
    out, applied = apply_kp_picks([r2], {"kp-bbbb2222": entry})
    assert applied == 1 and out[0]["name"] == "480G SATA SSD 企业级"


def test_legacy_text_keyed_pick_still_resolves():
    from app.services.part_selector import apply_kp_picks, pick_for_row
    r = _row("CPU", "2颗兆芯50000", "kp-cccc3333", "reg:CPU")
    legacy = {"CPU|2颗兆芯50000": {"name": "兆芯 KH50000 96C", "price": 9}}
    assert pick_for_row(legacy, "CPU", "2颗兆芯50000", row=r) is legacy["CPU|2颗兆芯50000"]
    out, applied = apply_kp_picks([r], legacy)
    assert applied == 1 and out[0]["name"] == "兆芯 KH50000 96C", "旧线程里的 picks 继续生效"


def test_ensure_pick_rows_uses_entry_identity_when_key_is_row_id():
    from app.services.part_selector import ensure_pick_rows
    entry = {"row_id": "kp-dddd4444", "origin": "cfg:NIC", "category": "NIC",
             "description": "2个万兆网口", "rev": "x", "name": "X710"}
    parts = ensure_pick_rows([], {"kp-dddd4444": entry})
    assert len(parts) == 1
    assert parts[0]["category"] == "NIC" and parts[0]["request_spec"] == "2个万兆网口"
    assert parts[0]["row_id"] == "kp-dddd4444" and parts[0]["origin"] == "cfg:NIC"


def test_waived_matches_row_id_and_origin_keys():
    from app.services.part_selector import apply_kp_waived
    r = _row("GPU", "8卡训练 GPU", "kp-eeee5555", "reg:GPU")
    out, n = apply_kp_waived([dict(r)], {"kp-eeee5555"})
    assert n == 1 and out[0]["waived"] is True
    out2, n2 = apply_kp_waived([dict(r)], {"reg:GPU"})
    assert n2 == 1 and out2[0]["waived"] is True


def test_bridge_ctx_shows_stale_pick_as_pending():
    from app.services.part_selector import row_content_rev
    from app.services.skill_node_plugins import plugin_for
    from app.services.skill_node_state import KP_PICKS, kp_state
    part = _row("Memory", "内存 512G DDR5", "kp-ffff6666", "reg:Memory")
    engine = {"ext": {"kp_rows": [{"part_category": "Memory", "description": "内存 512G DDR5"}]},
              "kp_parts": [part], "flow_configs": {}, "node_state": {}}
    kp_state(engine)[KP_PICKS] = {"kp-ffff6666": {
        "row_id": "kp-ffff6666", "category": "Memory", "description": "内存 512G DDR5",
        "rev": row_content_rev("Memory", "内存 512G DDR5"), "name": "64G RDIMM"}}
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    assert ctx["kp_rows_all"][0]["status"] == "已锁定"

    # 描述改成实质不同内容 → 同一行身份，但 pick 已 stale，必须回到待处理（重选）
    part2 = _row("Memory", "内存 1T DDR5", "kp-ffff6666", "reg:Memory")
    engine["kp_parts"] = [part2]
    engine["ext"] = {"kp_rows": [{"part_category": "Memory", "description": "内存 1T DDR5"}]}
    ctx2: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx2)
    row = ctx2["kp_rows_all"][0]
    assert row["row_id"] == "kp-ffff6666", "身份不变"
    assert row["status"] == "待处理", "内容改了 → 旧 pick 失效，该行必须重选"

# ── 8. P3-3：行引用只认身份；新增行必须显式声明，声明即铸身份（跨轮可引用）───

def _stub_name_lookup(rows: list):
    """落料按料号名回库核对：单测不碰 DB（2026-09-12 去台账，库内只有这些料号）。"""
    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        want = re.sub(r"\s+", "", str(name or "")).lower()
        hit = [r for r in rows if str(r.get("category")) == str(category)
               and re.sub(r"\s+", "", str(r.get("name") or "")).lower() == want]
        return {"ok": True, "category": category, "source": "kp_library/name_lookup",
                "rows": [dict(r) for r in hit], "total": len(hit)}
    return _by_name


def _select(args, *, engine=None, ext=None, rows=None, library=None):
    from app.services import data_tools, skill_tool_context, skill_tools_select
    engine = {} if engine is None else engine
    skill_tool_context.TOOL_CTX.set({
        "ext": ext if ext is not None else {}, "task_active": True, "engine": engine,
        "kp_rows_ctx": rows if rows is not None else [],
        "save": lambda: None})
    orig = data_tools.lookup_parts_by_name
    data_tools.lookup_parts_by_name = _stub_name_lookup(library or [])
    try:
        return skill_tools_select.tool_select_parts(args), engine
    finally:
        data_tools.lookup_parts_by_name = orig


def test_select_parts_rejects_unknown_ref_instead_of_guessing_a_row():
    """措辞漂移/未知引用一律 row_unknown + 可用 row_id 清单（拒绝机械正则）。"""
    row = _row("HDD/SSD", "系统盘 2块480G SSD", "kp-bbbb2222", "reg:HDD/SSD")
    row["row_key"] = "HDD/SSD|系统盘 2块480G SSD"
    res, engine = _select(
        {"picks": [{"row": "HDD/SSD|系统盘480G SSD ×2", "name": "480G SSD", "reason": "漂移"}]},
        rows=[row])
    assert res["ok"] is False
    assert res["results"][0]["error"] == "row_unknown"
    assert [c["row_id"] for c in res["results"][0]["rows"]] == ["kp-bbbb2222"]
    assert not ((engine.get("node_state") or {}).get("kp_reason") or {}).get("picks"), "解析不到就不落键"


def test_new_row_gate_requires_category_and_spec():
    """new_row=true 才铸新行；缺类目 / 缺描述逐级拒绝（不铸幽灵行）。"""
    res, _ = _select({"picks": [{"row": "NIC", "category": "NIC", "new_row": True, "reason": "r"}]},
                     library=_NIC_LIBRARY)
    assert res["results"][0]["error"] == "spec_required", "只给类目名不铸行"
    res2, _ = _select({"picks": [{"row": "2个万兆网口", "spec": "2个万兆网口",
                                  "new_row": True, "reason": "r"}]}, library=_NIC_LIBRARY)
    assert res2["results"][0]["error"] == "category_required"


_NIC_LIBRARY = [{"part_id": "701", "name": "X710 万兆双口", "category": "NIC", "price": 900.0}]


def test_declared_row_is_minted_immediately_and_pick_keyed_by_identity():
    """显式声明的新行当场铸 cfg: 身份，pick 按 row_id 落键——下一轮发布是同一个 id。"""
    res, engine = _select({"picks": [{"row": "NIC|2个万兆网口", "new_row": True,
                                      "name": "X710 万兆双口", "reason": "客户要万兆"}]},
                          library=_NIC_LIBRARY)
    assert res["ok"] is True, res
    st = (engine["node_state"] or {}).get("kp_reason") or {}
    config = st.get("config") or []
    assert [(r["category"], r["spec"]) for r in config] == [("NIC", "2个万兆网口")]
    rid = row_id_for_origin("cfg:NIC")
    # 客户没登记过该类目 → specified=False，只登记推荐（须反问）；键仍然是身份
    store = st.get("picks") or st.get("recommend") or {}
    assert list(store) == [rid], "声明行不必等下一轮发布，当场按身份落键"
    assert store[rid]["origin"] == "cfg:NIC"
    published = config_rows_to_parts(config)[0]
    assert published["row_id"] == rid, "下一轮发布铸出同一个 id（跨轮可引用）"


def test_select_parts_schema_carries_the_contract():
    """契约写在工具 schema（工具层真源），不写在提示词或策略中心里。"""
    from app.services.agent_tool_specs import _TOOL_SPECS
    props = _TOOL_SPECS["select_parts"]["parameters"]["properties"]["picks"]["items"]["properties"]
    assert "new_row" in props and "spec" in props
    assert "row_id" in props and "原文" in props["row_id"]["description"], "引用必须指向清单原文"
    assert "row_unknown" in props["row_id"]["description"], "解析不到的结果码要写进契约"

def test_row_list_publishes_one_entry_per_identity_for_combo_parts():
    """组合件（一行需求 = 多颗料）在 BOM 里是多条明细，但行清单按身份只发布一条（P3-4 实测）。

    实测线程 4a8cbfd2：NIC「4个千兆网口」被组合选成 3 颗料（网卡+两口+光模块），
    修复前权威行清单里同一个 row_id 出现 3 次，AI 没法引用。
    """
    from app.services.skill_node_plugins import plugin_for
    from app.services.skill_node_state import KP_PICKS, kp_state
    base = _row("NIC", "4个千兆网口", "kp-e13506ee", "reg:NIC#1")
    a = {**base, "unmatched": False, "name": "千兆四口（OCP）", "qty": 1}
    b = {**base, "unmatched": False, "name": "1G I350 4port", "qty": 1}
    engine = {"ext": {"kp_rows": [{"part_category": "NIC", "description": "4个千兆网口"}]},
              "kp_parts": [a, b], "flow_configs": {}, "node_state": {}}
    kp_state(engine)[KP_PICKS] = {"kp-e13506ee": [
        {"row_id": "kp-e13506ee", "category": "NIC", "description": "4个千兆网口",
         "name": "千兆四口（OCP）"},
        {"row_id": "kp-e13506ee", "category": "NIC", "description": "4个千兆网口",
         "name": "1G I350 4port"}]}
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    assert [r["row_id"] for r in ctx["kp_rows_all"]] == ["kp-e13506ee"], (
        "同一 row_id 在权威行清单里只能出现一次")
    assert ctx["kp_rows_all"][0]["status"] == "已锁定"
    assert ctx["kp_rows_all"][0]["part"] == "千兆四口（OCP）+1G I350 4port", "组合明细合成一条"
    assert ctx["kp_rows_ctx"] == [], "已锁定行不进待选型清单"
