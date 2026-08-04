# -*- coding: utf-8 -*-
"""R25/R26 + I22 + I30 回归：L6 riser 描述派生（高带宽网卡）、RAID 按机型兼容、GPU 同性能替代。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[0]))

import json

from app.services.bom_template_eval import eval_l6_rows
from sqlalchemy import text
from app.models.base import l6_engine

_STD = {"IO1": "1*X8 FHFL", "IO2": "1*X8 FHFL"}   # 测试数据（规则验证用）
_X16 = "1*X16+1*X8 FHFL"


def _set_cc(extra):
    with l6_engine.begin() as c:
        r = c.execute(text("SELECT config_content FROM l6.base_configs WHERE id=18")).mappings().first()
        cc = r["config_content"] if r else None
        if isinstance(cc, str):
            cc = json.loads(cc)
        cc = dict(cc or {})
        cc.pop("standard_riser", None)
        cc.pop("riser_x16", None)
        cc.update(extra)
        c.execute(text("UPDATE l6.base_configs SET config_content=:cc WHERE id=18"),
                  {"cc": json.dumps(cc, ensure_ascii=False)})


def _io_rows(kp, signals=None):
    rows = eval_l6_rows(1, 18, kp, signals or {"psu_wattage": "1300", "psu_qty": 2})
    return {r["catalogue"]: r["description"] for r in rows if r["catalogue"] in ("IO1", "IO2")}


def test_riser_no_data_leaves_empty():
    """R27：未配置 standard_riser/riser_x16 → IO 行留空手填（拒绝硬编码）。"""
    _set_cc({})
    d = _io_rows([{"category": "CPU", "qty": 2, "hint": "9554"}])
    assert d == {"IO1": "", "IO2": ""}


def test_riser_no_gpu_no_100g_uses_standard():
    _set_cc({"standard_riser": _STD})
    d = _io_rows([{"category": "CPU", "qty": 2, "hint": "9554"}])
    assert d == {"IO1": "1*X8 FHFL", "IO2": "1*X8 FHFL"}


def test_riser_gpu_all_x16():
    _set_cc({"standard_riser": _STD, "riser_x16": _X16})
    d = _io_rows([{"category": "GPU", "qty": 1, "hint": "H100"}])
    assert d == {"IO1": "1*X16+1*X8 FHFL", "IO2": "1*X16+1*X8 FHFL"}


def test_riser_100g_nic_io1_x16():
    """R26：无 GPU 但有 100G 网卡（x16 卡）→ IO1 升级 x16、IO2 按标准（YC-0722 样本）。"""
    _set_cc({"standard_riser": _STD, "riser_x16": _X16})
    d = _io_rows([{"category": "Network(NIC) requirement", "qty": 1, "hint": "100G 2port"}])
    assert d["IO1"] == "1*X16+1*X8 FHFL"
    assert d["IO2"] == "1*X8 FHFL"


def test_riser_10g_nic_no_upgrade():
    _set_cc({"standard_riser": _STD, "riser_x16": _X16})
    d = _io_rows([{"category": "Network(NIC) requirement", "qty": 1, "hint": "10G 2port"}])
    assert d == {"IO1": "1*X8 FHFL", "IO2": "1*X8 FHFL"}


def test_raid_applicable_orion_default_9540():
    """I22：需求只写 RAID 级别 → 按配件库 applicable.series 兼容机型选件（Orion 默认 9540-8i）。"""
    from app.api.candidate_search import pick_kp_parts
    out = pick_kp_parts(["Raid card"], ["raid", "0", "1", "10"],
                        platform_series="Orion", qty_map={"Raid card": 1})
    raid = [r for r in out if "raid" in (r.get("category") or "").lower() or "阵列" in (r.get("category") or "")]
    assert raid and "9540" in (raid[0].get("name") or "")


def test_gpu_substitution_by_vram():
    """I30：需求 GPU 型号库里无 → 按显存容量找同性能替代，透明标注，不 unmatched。"""
    from app.api.candidate_search import pick_kp_parts
    out = pick_kp_parts(["GPU"], ["rtxpro4500", "32g"],
                        gpu_groups=[{"term": "RTX PRO 4500", "qty": 1, "cap": 32, "tokens": ["rtxpro4500"]}],
                        qty_map={"GPU": 1})
    gpu = [r for r in out if (r.get("category") or "") == "GPU"]
    assert gpu and not gpu[0].get("unmatched")
    assert "替代" in (gpu[0].get("matched_spec") or "")


def test_raid_groups_pick_exact_models():
    """R28（ESA24V3-P）：需求显式 LSI 9560 16i / LSI 9364 8i → 按组精确出件（不落 9540-8i 泛配）。"""
    from app.api.candidate_search import _pick_raid_groups
    from app.repository.kp_repo import KPRepository
    kp = KPRepository()
    try:
        out = []
        produced = _pick_raid_groups(
            [{"model": "9560-16i", "qty": 1, "cache": "8"},
             {"model": "9364-8i", "qty": 1, "cache": "2"}],
            "Raid card", kp,
            lambda parts: min(parts, key=lambda p: p.get("price") or 0), out)
        assert produced == 2, out
        models = {o.get("pn") for o in out}
        assert "LSI 9560-16i" in models and "LSI 9364-8i" in models, models
        assert any("9560-16i" in (o.get("matched_spec") or "") for o in out)
    finally:
        kp.close()
