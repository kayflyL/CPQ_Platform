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


def test_raid_groups_pick_exact_models():
    """R28（ESA24V3-P）：需求显式 LSI 9560-16i / LSI 9364-8i → 引擎只产缺口行，候选池确含真实料号。"""
    from app.services.part_selector import retrieve_part_candidates, select_parts
    out = select_parts(
        categories=["Raid card"],
        raid_groups=[
            {"model": "9560-16i", "qty": 1},
            {"model": "9364-8i", "qty": 1},
        ],
    )
    assert len(out) == 2 and all(r.get("unmatched") for r in out)
    pools = retrieve_part_candidates(categories=["Raid card"])
    models = {c.get("model") or "" for rows in pools.values() for c in rows}
    assert any("LSI 9560-16i" in m for m in models), sorted(models)[:5]
    assert any("LSI 9364-8i" in m for m in models), sorted(models)[:5]



def test_gpu_missing_model_does_not_silently_fallback():
    """GPU 型号库内缺失时，引擎不按显存容量替换成别的可售型号，只交还 AI 选型缺口。"""
    from app.services.part_selector import select_parts
    out = select_parts(
        categories=["GPU"],
        gpu_groups=[{"tokens": ["rtxpro4500"], "qty": 1, "cap": 32}],
    )
    gpu = [r for r in out if (r.get("category") or "") == "GPU"]
    assert gpu, out
    assert gpu[0].get("unmatched") is True
    assert gpu[0].get("pn") == ""
    assert "rtxpro4500" in (gpu[0].get("request_spec") or "")


