# -*- coding: utf-8 -*-
"""I37/I38 回归：网卡数量错绑（PCIe x16 当数量、行级 qty 丢失）+ RAID1 当型号。

R2 需求（2026-08-03 训练）：
  - "2* pcie x16 +4* pcie x8" 的 x16/x8 曾把 16 绑到网卡品类 → 3 行网卡全 ×16（I37）；
  - "2* ConnectX-6 Dx dual 25G SFP28" 行内数量 2 丢失 → 多余 ×1 行（I37）；
  - "2* 480GB SATA SSD （RAID1）" 的 RAID1 被当型号 → 命中库中同名件，480G 出两行（I38）。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_nic_qty_binding.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from app.repository.reasoning_flow_repo import _default_node_configs
from app.services.requirement_intel_service import (_fold_lexicons,
                                                    _nic_line_filters,
                                                    extract_keywords)
def run_requirement_pipeline(text: str, model_index: int = 0) -> tuple:
    """端到端跑需求分析管道（extract→select→pick→build），返回 (plan, ext)。
    注：golden/compare_bom 已随「回归中心」砍掉，本函数保留在测试内自包含（行为单测用）。"""
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    from app.api.candidate_search import (select_models, pick_kp_parts, build_plan,
                                         kp_categories_for_type, build_variant_signals)
    from app.services.reasoning_executor import _resolve_budget_strategy
    from app.services.requirement_normalizer import normalize_text

    text, _norm_report = normalize_text(text, _default_node_configs().get("normalize_input") or {})
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords(text, lexicon=cat_lex, series_keyword_map=series_map,
                           usage_keyword_map=usage_map, form_keyword_map=form_map,
                           chassis_lexicon=chassis_lex,
                           spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                           qty_multipliers=cfg.get("qty_multipliers"),
                           model_token_regex=cfg.get("model_token_regex"))
    from app.api.candidate_search import MAX_PLANS as _MAX_PLANS
    models = select_models(ext.get("usage"), ext.get("server_type_name"), ext.get("series"),
                           ext.get("form"), limit=_MAX_PLANS,
                           no_signal_strategy=_default_node_configs()["select_baseline"].get("no_signal_strategy"),
                           variant_signals=build_variant_signals(ext, text))
    if not models:
        return None, ext
    bl = models[model_index] if model_index < len(models) else models[0]
    _mk_cfg = _default_node_configs()["match_kp"]
    type_cats = kp_categories_for_type(bl.get("server_type_name") or "", _mk_cfg.get("type_packages"), ext.get("categories"))
    eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
    bl_kp = pick_kp_parts(eff_cats, ext.get("keywords", []),
                          representative_pick=_resolve_budget_strategy(ext.get("budget")),
                          spec_rules=_mk_cfg.get("spec_rules"),
                          fallback_strategy="fallback_representative",
                          requirement_text=text,
                          qty_map=ext.get("qty_map"),
                          qty_per_token=ext.get("qty_per_token"),
                          spec_search_terms=ext.get("spec_search_terms"),
                          model_token_regex=cfg.get("model_token_regex"),
                          mem_signal=ext.get("mem_signal"),
                          cpu_signal=ext.get("cpu_signal"),
                          multi_spec_filters=ext.get("multi_spec_filters"),
                          drive_groups=ext.get("drive_groups"),
                          gpu_groups=ext.get("gpu_groups"),
                          mem_groups=ext.get("mem_groups"),
                          drive_spec_substitute=(_default_node_configs().get("match_kp") or {}).get("drive_spec_substitute", True),
                          platform_series=bl.get("series"))
    p = build_plan(bl, bl_kp)
    _cs = p.get("chassis_signals") or {}
    _sig_w = (ext.get("psu_signal") or {}).get("wattage")
    _sig_q = (ext.get("psu_signal") or {}).get("qty")
    if _sig_w:
        _cs = {**_cs, "psu_wattage": _sig_w}
    if _sig_q:
        _cs = {**_cs, "psu_qty": int(_sig_q)}
    p["chassis_signals"] = _cs
    return p, ext


def system_kp_rows(plan: dict) -> list[dict]:
    """plan → 系统 KP 行 [{category, pn, qty, unmatched}]。"""
    rows = []
    for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []:
        if r.get("category") != "Key Parts":
            continue
        rows.append({"category": r.get("part_category") or r.get("catalogue") or "",
                     "pn": r.get("catalogue") or "", "qty": r.get("qty") or 1})
    for u in plan.get("unmatched") or []:
        rows.append({"category": u.get("category") or "型号未命中", "pn": "", "qty": 0, "unmatched": True,
                     "reason": u.get("reason") or ""})
    return rows

R2 = """2* AMD EPYC 9554 64 128  3.75 GHz 3.1 GHz 256 MB 360W
16* 32GB DDR5 ECC RDIMM （512GB）
1* NVIDIA H100 PCIe 80GB
2* 480GB SATA SSD （RAID1）
4* 7.68 TB Enterprise-class SSD No less than 1 DWPD
1* 1.6T or 1.92T Enterprise-class storage No less than 3 DWPD (Drive Writes Per Day)
1* Broadcom HBA 9500-8i
2* ConnectX-6 Dx dual 25G SFP28
4* SFP28 25 Gb/s transmission modules
2* 2000W 80 Plus Platinum
2* pcie x16 +4* pcie x8
2* H100 power cable"""

R4 = """Hi Rowling, can help for 27 unit server with 2x 32 core 9005series of AMD EPYC or Intel Xeon 6 , (2TB Memory RDIMM@128 GB each), 2 x 25 GB SFP28, 1 x IPMI RJ45, 2 x 32GB Fibre Channel HBA. Rackmount 2U, 12/24 bays HDDSupport of NVMe, Redundant PSU.16:50"""


def _extract(text):
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    return extract_keywords(text, lexicon=cat_lex, series_keyword_map=series_map,
                            usage_keyword_map=usage_map, form_keyword_map=form_map,
                            chassis_lexicon=chassis_lex,
                            spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                            qty_multipliers=cfg.get("qty_multipliers"),
                            model_token_regex=cfg.get("model_token_regex"))


# ============================================================
# I37A：PCIe 槽位 xN（x16/x8）不得当数量
# ============================================================

def test_pcie_x16_not_bound_to_nic_qty():
    ext = _extract(R2)
    nic_qty = ext["qty_map"].get("Network(NIC) requirement", 0)
    assert nic_qty not in (16, 8), f"pcie x16/x8 被当数量：NIC qty={nic_qty}"
    assert ext["qty_map"].get("Memory") == 16          # 内存数量不受影响


# ============================================================
# I37B：网卡行内数量（前缀 N* 型号 / 后缀 型号*N）
# ============================================================

def test_nic_lines_carry_per_line_qty():
    ext = _extract(R2)
    lines = ext["multi_spec_filters"]["Network(NIC) requirement"]
    assert len(lines) == 2, f"同一物理行应去重成 2 行，实际 {len(lines)}: {lines}"
    assert sorted(int(l.get("qty") or 0) for l in lines) == [2, 4]


def test_nic_line_prefix_and_suffix_qty():
    assert _nic_line_filters("2* connectx-6 dx dual 25g sfp28")["qty"] == 2   # 前缀
    assert _nic_line_filters("25G双口含光模块*2")["qty"] == 2                   # 后缀
    assert _nic_line_filters("1 *双口万兆")["qty"] == 1                          # 前缀带空格
    line = _nic_line_filters("PCIe4.0 x16")                                     # 0x16 不当数量
    assert line.get("qty") is None


# ============================================================
# I38：RAID 级别（RAID1/5/10）不是型号 token
# ============================================================

def test_raid_level_not_keyword():
    ext = _extract(R2)
    assert not any(str(k).lower().startswith("raid") for k in ext.get("keywords") or [])


# ============================================================
# 端到端：R2 全链路
# ============================================================

def test_pipeline_r2_nic_no_x16_and_correct_qty():
    plan, _ = run_requirement_pipeline(R2)
    rows = [r for r in system_kp_rows(plan) if "NIC" in str(r.get("category") or "")]
    qtys = [int(r["qty"]) for r in rows]
    assert 16 not in qtys and 8 not in qtys
    assert sorted(qtys) == [2, 4]


def test_pipeline_r2_raid1_no_duplicate_drive_row():
    plan, _ = run_requirement_pipeline(R2)
    rows = [r for r in system_kp_rows(plan) if "HDD/SSD" in str(r.get("category") or "")]
    g480 = [r for r in rows if "480" in str(r.get("pn") or "")]
    assert len(g480) == 1, f"480G 应只有一行：{[(r['pn'], r['qty']) for r in g480]}"
    assert int(g480[0]["qty"]) == 2


# ============================================================
# I20：字母 x「N x 速率」= 端口数不是卡数（"2 x 25 GB SFP28" = 1 张双口卡）
# ============================================================

def test_nic_letter_x_is_port_count_not_card_qty():
    line = _nic_line_filters("2 x 25 GB SFP28")
    assert line.get("qty") is None, f"2 x 25G 的 2 是端口数，不得当卡数量：{line}"
    assert any(f.get("spec_key") == "Ports" and f.get("value") == "2" for f in line["filters"]), line


def test_nic_symbol_multiplier_still_card_qty():
    # 符号乘号（* / ×）仍是卡数量：2 张双口 25G
    assert _nic_line_filters("2* connectx-6 dx dual 25g sfp28")["qty"] == 2
    assert _nic_line_filters("2× 25G双口")["qty"] == 2


def test_drive_cap_multiplier_not_affected_by_nic_skip():
    # I20 跳过只影响「N x 速率 + 网卡上下文」；"2×480GB SSD"（盘数量）必须保留
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords("2×480GB SSD 系统盘", lexicon=cat_lex, series_keyword_map=series_map,
                           usage_keyword_map=usage_map, form_keyword_map=form_map,
                           chassis_lexicon=chassis_lex, spec_aliases=cfg.get("spec_aliases"),
                           qty_units=cfg.get("qty_units"), qty_multipliers=cfg.get("qty_multipliers"),
                           model_token_regex=cfg.get("model_token_regex"))
    assert ext["qty_map"].get("HDD/SSD") == 2


def test_pipeline_r4_nic_single_dual_port_card():
    # R4 端到端：2 x 25 GB SFP28 → 1 张双口 25G 卡（技术员 1 张，I20）
    plan, _ = run_requirement_pipeline(R4)
    rows = [r for r in system_kp_rows(plan) if "NIC" in str(r.get("category") or "") and "25G" in str(r.get("pn") or "")]
    assert rows, "R4 应有 25G 网卡行"
    assert int(rows[0]["qty"]) == 1, f"应 1 张双口卡，实际 {rows[0]['qty']}: {rows[0]['pn']}"

