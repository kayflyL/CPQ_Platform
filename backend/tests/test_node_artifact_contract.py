# -*- coding: utf-8 -*-
"""节点产物契约回归（Step 6 + Step 7）。

插座 = 节点机制（skill_node_artifacts 注册表 + 主循环）；插头 = target.artifacts[]（DB）。
本文件锁住「换目标层不碰代码生效」：
  1) 产物分发只认抽屉声明的 slot——代码里没有「节点 → 产物」兜底表；
  2) 每个节点的产物都取自引擎事实（各节点产物槽），不是另建的一份表；
  3) 改抽屉 slot / 列定义 → 节点产物跟着变，主循环代码零改动；
  4) 未声明 slot / slot 未注册 → 产物为空（白盒不装懂，不猜）；
  5) 边沿一致性：列契约的 from/fallback 在真实行数据上取不出值即判红；
  6) 真实抽屉配置（DB）对每个节点都声明了已注册的产物槽。
"""
from app.services import skill_tools_fill
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import skill_node_artifacts as art_mod
from app.services.skill_node_artifacts import (
    BUILDERS, node_payload, resolve_kind)
from app.services.skill_target_contract import validate_artifact


def _drawer() -> dict:
    """真实抽屉配置（DB 唯一权威：默认契约 + 该流增量）。"""
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="需求分析")
    finally:
        repo.close()
    assert flow, "需求分析流程未配置"
    return flow.get("node_configs") or {}


def _engine_for(key: str) -> dict:
    if key == "input":
        return {"requirement_text": "需要一台通用计算服务器，AMD 平台", "opportunity_id": "o1"}
    if key == "agent_fill":
        return {"ext": {"server_type": "通用计算服务器", "purchase_qty": 1}}
    if key == "model_reason":
        # 无 id → L6 行求值不碰库（本用例只验产物形状与 slot 分发）
        return {"_locked_baseline": {"name": "ZS220 V2"}, "lock_reason": "目录唯一命中",
                "baselines_pool": [{"name": "ZS220 V2"}]}
    if key == "kp_reason":
        return {"kp_summary": {"kp_count": 1, "unmatched_count": 0},
                "kp_parts": [{"category": "CPU", "name": "兆芯 KH-50000 96C", "qty": 2,
                              "request_spec": "2颗兆芯50000 96C", "unmatched": False}]}
    if key == "compose":
        return {"plans": [{"model": "ZS220 V2",
                           "cfg": {"bom_excel_rows": [
                               {"category": "L6", "catalogue": "ZS220 V2", "qty": 1},
                               {"category": "Key Parts", "part_category": "CPU",
                                "catalogue": "兆芯 KH-50000 96C", "qty": 2}]}}]}
    if key == "output":
        return {"plans": [{"model": "ZS220 V2"}],
                "output_payload": {"ok": True, "configs": [{"server_model": "ZS220 V2"}]}}
    return {}


def _plug(slot: str, **extra) -> dict:
    return {"target": {"artifacts": [{"slot": slot, **extra}]}}


# ── 1. 分发只认抽屉声明的 slot ────────────────────────────────────────────────

def test_no_per_node_product_table_in_code():
    """代码里不得再有「节点 → 产物」兜底表：产物槽只由抽屉声明。"""
    assert not hasattr(art_mod, "DEFAULT_KIND_BY_NODE")
    src = open(art_mod.__file__, encoding="utf-8").read()
    assert "DEFAULT_KIND_BY_NODE" not in src
    # 没声明 slot 的节点（无论叫什么名字）一律没有产物槽
    for key in ("agent_fill", "kp_reason", "compose", "任何新节点"):
        assert art_mod.resolve_kind({"flow_configs": {}}, key) == ""


def test_drawer_slot_decides_the_product():
    engine = _engine_for("compose")
    engine["flow_configs"] = {"compose": _plug("kp_table", name="配件表")}
    assert resolve_kind(engine, "compose") == "kp_table"
    payload = node_payload(engine, "compose", "BOM 组装", "s")
    assert payload["artifact"]["kind"] == "kp_table"


def test_render_kind_alone_does_not_pick_a_slot():
    """只声明渲染类型（table/form）不构成产物槽：产物为空，不按节点名兜底。"""
    engine = _engine_for("compose")
    engine["flow_configs"] = {"compose": {"target": {"artifacts": [{"kind": "table"}]}}}
    assert resolve_kind(engine, "compose") == ""
    payload = node_payload(engine, "compose", "BOM 组装", "")
    assert payload["artifact"] is None and payload["output"] is None
    assert "未注册产物" in payload["summary"]


def test_legacy_output_artifact_binds_only_when_it_names_a_slot():
    """过渡期兼容：output_artifact 值恰好是已注册产物槽时才算声明；否则不猜。"""
    engine = {"flow_configs": {"output": {"output_artifact": "requirement_text"}}}
    assert resolve_kind(engine, "output") == "requirement_text"
    engine = {"flow_configs": {"output": {"output_artifact": "ext / requirement"}}}
    assert resolve_kind(engine, "output") == ""


def test_legacy_string_target_is_not_a_plug():
    """交付节点历史配置的 target 是产物引用字符串，不是插头字典——不得抛错。"""
    from app.services.skill_target_contract import first_artifact, target_artifacts
    cfg = {"output_kind": "bom_scheme_draft", "target": "bom_scheme",
           "payload_map": {"plans": "ctx.plans"}}
    assert target_artifacts(cfg) == []
    assert first_artifact(cfg) == {}


def test_a_string_target_cannot_clobber_the_drawer_plug():
    """同名不同义的历史字段：config.target 曾是「交接目标字符串」。

    产物槽是插头（target.artifacts）。一旦被字符串覆盖，resolve_kind 就找不到槽 →
    节点下产物凭空消失（画布上「只有登记节点还有输出物」那类事故的根因）。
    """
    from app.services import reasoning_node_contract as contract
    for key in ("input", "agent_fill", "model_reason", "kp_reason", "compose", "output"):
        cfg = contract.effective_config(key, {"target": "bom_scheme"})
        assert isinstance(cfg.get("target"), dict), f"{key} 的产物槽被字符串 target 冲掉"
        assert resolve_kind({"flow_configs": {key: cfg}}, key), f"{key} 节点下产物会消失"


def test_swapping_drawer_slot_changes_payload_without_code_change():
    engine = _engine_for("compose")
    engine["flow_configs"] = {"compose": _plug("kp_table", name="配件表")}
    assert node_payload(engine, "compose", "BOM 组装", "s")["artifact"]["kind"] == "kp_table"
    engine["flow_configs"] = {"compose": _plug("plans", name="方案配置表")}
    assert node_payload(engine, "compose", "BOM 组装", "s")["artifact"]["kind"] == "plans"


def test_target_columns_drive_artifact_columns():
    """换列定义：抽屉 columns → 产物 columns（visible 过滤），代码零改动。"""
    engine = _engine_for("kp_reason")
    engine["flow_configs"] = {"kp_reason": _plug(
        "kp_table", name="配件表", columns=[
            {"key": "part_category", "label": "Catalogue"},
            {"key": "qty", "label": "Quantity"},
            {"key": "catalogue", "label": "Desc", "visible": False}])}
    cols = node_payload(engine, "kp_reason", "配件选型", "s")["artifact"]["data"]["columns"]
    assert [c["key"] for c in cols] == ["part_category", "qty"]


# ── 2. 产物形状：每节点一条（产物 = 引擎事实，不是另建的表）──────────────────

def test_payload_carries_node_artifact_from_engine_facts():
    cfgs = _drawer()
    expected = {"input": "requirement_text", "agent_fill": "requirement_slots",
                "model_reason": "l6_chassis", "kp_reason": "kp_table",
                "compose": "plans", "output": "bom_scheme"}
    for key, slot in expected.items():
        engine = _engine_for(key)
        engine["flow_configs"] = cfgs
        assert resolve_kind(engine, key) == slot, f"{key} 抽屉声明的产物槽不是 {slot}"
        payload = node_payload(engine, key, key, "s")
        assert payload["status"] == "done"
        assert payload["artifact"] is not None, f"{key} 节点下没有输出物"
        assert payload["artifact"]["kind"] == slot
        assert payload["artifact"]["title"], f"{key} 产物缺标题"


def test_input_node_artifact_is_requirement_text():
    engine = _engine_for("input")
    engine["flow_configs"] = _drawer()
    payload = node_payload(engine, "input", "输入", "")
    art = payload["artifact"]
    assert art["kind"] == "requirement_text"
    assert art["data"]["text"].startswith("需要一台通用计算服务器")
    assert payload["summary"], "摘要由产物生成，不得为空"


def test_kp_artifact_rows_use_real_engine_parts():
    engine = _engine_for("kp_reason")
    engine["flow_configs"] = _drawer()
    payload = node_payload(engine, "kp_reason", "配件选型", "s")
    rows = payload["artifact"]["data"]["rows"]
    assert rows[0]["part_category"] == "CPU"
    assert rows[0]["catalogue"] == "兆芯 KH-50000 96C"
    assert rows[0]["qty"] == 2
    assert payload["artifact"]["data"]["summary"]["kp_count"] == 1


def test_compose_payload_carries_assembled_sheet_rows():
    """组装节点产物 = 完整方案配置表行（L6 + KP 组装结果），不是只有方案计数。"""
    engine = _engine_for("compose")
    engine["flow_configs"] = _drawer()
    data = node_payload(engine, "compose", "BOM 组装", "s")["artifact"]["data"]
    assert data["plans_count"] == 1
    assert [r["catalogue"] for r in data["rows"]] == ["ZS220 V2", "兆芯 KH-50000 96C"]
    assert [r["qty"] for r in data["rows"]] == [1, 2]
    assert [c["key"] for c in data["columns"]] == ["part_category", "catalogue", "qty"]


def test_output_node_carries_bom_scheme_card():
    engine = _engine_for("output")
    engine["flow_configs"] = _drawer()
    payload = node_payload(engine, "output", "输出", "已生成整机方案")
    assert payload["artifact"]["kind"] == "bom_scheme"
    assert payload["artifact"]["data"] == engine["output_payload"]


# ── 3. 登记表契约：由目标层插头解释，不再有 kind=form 特判 ───────────────────

def test_fill_contract_comes_from_target_layer_not_node_special_case():
    """登记契约 = 目标层插头（slot=requirement_slots）解释结果。

    字段/部件大类/值域来自配置与数据；填写规则属于节点说明（抽屉 description）与工具
    schema，契约不二次复述（同一个规则只允许有一处权威）。
    """
    from app.services.skill_tools_fill import _fill_contract_brief
    from app.services.slot_contract import slot_spec
    from app.services.catalog_options import catalog_whitelist
    brief = _fill_contract_brief()
    keys = [str(s.get("key")) for s in slot_spec() if s.get("src_type") != "kp"]
    assert keys, "登记表字段契约为空？"
    assert all(k in brief for k in keys)
    wl = catalog_whitelist({}, {}, "")
    cand_vals = [str(v) for src in ("types", "series", "forms") for v in (wl.get(src) or []) if str(v).strip()]
    assert cand_vals, "在售目录为空？"
    assert any(v in brief for v in cand_vals)
    assert "兆芯50000" not in brief
    assert "replace=true" not in brief, "调用约定归工具 schema，不在目标层契约里复述"


def test_fill_contract_follows_target_layer_config():
    """换目标层名称 → 契约标题跟着变（证明契约真的由插头生成，不是节点硬编码）。"""
    from app.services.skill_node_plugins import fill_contract_brief
    cfg = {"target": {"artifacts": [{"slot": "requirement_slots", "name": "MY_TABLE"}]}}
    assert "MY_TABLE" in fill_contract_brief(cfg)


# ── 4. 边沿一致性护栏 ────────────────────────────────────────────────────────

def test_edge_contract_flags_unresolved_columns():
    art = {"kind": "table", "columns": [
        {"key": "part_category", "from": "part_category"},
        {"key": "catalogue", "from": "catalogue", "fallback": "name"},
        {"key": "ghost", "from": "not_a_field"}]}
    vr = validate_artifact(art, {"part_category": "CPU", "catalogue": "兆芯 KH-50000 96C"})
    assert vr["ok"] is False
    assert vr["unresolved_columns"] == ["ghost"]


def test_edge_contract_flags_duplicate_or_blank_column_keys():
    art = {"kind": "table", "columns": [
        {"key": "a", "from": "a"}, {"key": "a", "from": "a"}, {"key": "", "from": "b"}]}
    vr = validate_artifact(art, {"a": "x"})
    assert vr["ok"] is False
    assert vr["broken_columns"] == ["a", ""]


def _raw_rows(key: str, engine: dict) -> list:
    """该节点的**上游行数据**（列契约要取值的原始行，不是整形后的展示行）。"""
    if key == "kp_reason":
        return [p for p in (engine.get("kp_parts") or []) if isinstance(p, dict)]
    if key == "compose":
        out = []
        for p in (engine.get("plans") or []):
            out += [r for r in ((p.get("cfg") or {}).get("bom_excel_rows") or [])
                    if isinstance(r, dict)]
        return out
    return []


def test_drawer_column_contract_resolves_on_raw_rows():
    """契约级边沿一致性：抽屉列契约的 from/fallback 必须能在上游原始行上取值。

    列契约（from/fallback）指向的是**行数据字段**；取值链断掉 = 渲染出空列，
    这里判红，不等到画布上才发现。
    """
    from app.services.skill_target_contract import first_artifact
    cfgs = _drawer()
    for key in ("kp_reason", "compose"):
        art = first_artifact(cfgs.get(key) or {})
        assert art.get("columns"), f"{key} 抽屉没声明列契约"
        rows = _raw_rows(key, _engine_for(key))
        assert rows, f"{key} 没有可校验的上游行"
        vr = validate_artifact(art, rows[0])
        assert vr["ok"] is True, f"{key} 抽屉列契约取不到值：{vr}"


def test_builtin_fallback_columns_resolve_on_raw_rows():
    """内置兜底列契约必须与上游原始行自洽（防止改了行字段名忘改契约）。"""
    from app.services.skill_node_artifacts import (COMPOSE_FALLBACK_COLUMNS,
                                                   KP_TABLE_FALLBACK_COLUMNS)
    kp = _engine_for("kp_reason")
    kp_rows = _raw_rows("kp_reason", kp)
    assert kp_rows, "样本行缺失"
    kp_contract = [{"key": "catalogue", "from": "catalogue", "fallback": "name|request_spec"},
                   {"key": "qty", "from": "qty", "fallback": "1"}]
    assert validate_artifact({"kind": "table", "columns": kp_contract}, kp_rows[0])["ok"] is True
    assert KP_TABLE_FALLBACK_COLUMNS, "KP 兜底列不见了"
    cp_rows = _raw_rows("compose", _engine_for("compose"))
    assert validate_artifact({"kind": "table", "columns": COMPOSE_FALLBACK_COLUMNS},
                             cp_rows[0])["ok"] is True


# ── 5. 真实抽屉配置 × 产物打包（换插头零改主循环的回归口）────────────────────

def test_live_drawer_declares_registered_slot_for_every_node():
    """每个节点在真实抽屉里都声明了产物槽，且该槽已注册（漏配 = 画布上没有输出物）。"""
    cfgs = _drawer()
    for key in ("input", "agent_fill", "model_reason", "kp_reason", "compose", "output"):
        slot = resolve_kind({"flow_configs": cfgs}, key)
        assert slot, f"{key} 抽屉没声明产物槽（slot）"
        assert slot in BUILDERS, f"{key} 声明的产物槽 {slot} 未注册"


def test_live_drawer_config_never_breaks_payload_build():
    cfgs = _drawer()
    for key in ("input", "agent_fill", "model_reason", "kp_reason", "compose", "output"):
        engine = _engine_for(key)
        engine["flow_configs"] = cfgs
        payload = node_payload(engine, key, key, "s")
        assert payload["status"] == "done"
        assert payload["artifact"] is not None, f"{key} 节点下没有输出物"
