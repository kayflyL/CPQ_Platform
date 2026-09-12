# -*- coding: utf-8 -*-
"""混合检索实测电池（2026-09-12 P1 验收）：模拟各种用户需求口径，对照
纯词法（P0 part_query）vs 混合（词法+语义+RRF hybrid_search）。

用法：.venv/Scripts/python.exe -X utf8 scripts/hybrid_battery.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_tools import part_query
from app.services.part_search import hybrid_search
from app.services import part_search_index as psi

# (标签, category, text, spec_filters, series, 期望含, 期望不含)
CASES = [
    ("口语长句·两张万兆光口网卡", "NIC", "两张万兆光口网卡", None, "", ["10G"], ["I350"]),
    ("口语·千兆四口", "NIC", "千兆四口", None, "", ["I350", "4port"], None),
    ("型号词·9361 带 1G 缓存", "Raid card", "9361 1G缓存", None, "", ["9361"], None),
    ("品牌·沐曦 GPU", "GPU", "沐曦", None, "", ["沐曦"], None),
    ("错写别名·智凯100", "GPU", "智凯100", None, "", ["智铠"], ["H100"]),
    ("规格组合·1.92T SATA 固态", "HDD/SSD", "1.92T SATA 固态硬盘", None, "", ["SATA"], ["NVMe"]),
    ("规格过滤·DDR5 64G", "Memory", "64G",
     [{"spec_key": "Type", "op": "=", "value": "DDR5"}], "", ["DDR5"], ["DDR4"]),
    ("语义长尾·训练加速卡", "GPU", "机器学习训练用的加速卡", None, "", None, None),
    ("语义长尾·多口网络接口部件", "NIC", "多口网络接口部件", None, "", None, None),
    ("无料真话·HBM3e 141G", "GPU", "HBM3e 141G 显存", None, "", None, None),
    ("系列作用域·Polaris 找兆芯", "CPU", "兆芯 50000 96C", None, "Polaris", ["KH50000"], None),
    ("系列挡门·Orion 找兆芯", "CPU", "兆芯 50000 96C", None, "Orion", None, None),
    ("容量口语·2T 固态硬盘", "HDD/SSD", "2T 固态硬盘", None, "", None, None),
]


def _names(res, n=3):
    return [r["name"][:34] for r in (res.get("rows") or [])[:n]]


def _judge(res, must, ban):
    names = " | ".join(_names(res, 6))
    if res.get("out_of_scope") or res.get("scope_note"):
        return "SCOPE"
    if not (res.get("rows") or []):
        return "ZERO" + ("(note)" if res.get("note") else "")
    if must and not any(m in names for m in must):
        return "MISS"
    if ban and any(b in names for b in ban):
        return "FALSE+"
    return "PASS"


def main():
    print("semantic_available:", psi.semantic_available())
    t0 = time.time()
    lex_ok = hyb_ok = 0
    for label, cat, text, sf, series, must, ban in CASES:
        lx = part_query(cat, keywords=text, spec_filters=sf, series=series, limit=6)
        hy = hybrid_search(cat, text=text, spec_filters=sf, series=series, limit=6)
        jl, jh = _judge(lx, must, ban), _judge(hy, must, ban)
        lex_ok += jl.startswith("PASS")
        hyb_ok += jh.startswith("PASS") or jh == "SCOPE"
        ch = hy.get("channels") or {}
        print(f"\n== {label}")
        print(f"   词法[{jl:8}] {_names(lx)}")
        print(f"   混合[{jh:8}] {_names(hy)}  ch=lex:{ch.get('lexical')},sem:{ch.get('semantic')}")
        top = (hy.get("rows") or [{}])[0]
        if top.get("match"):
            print(f"   首条溯源 match={top['match']}")
        if jh == "SCOPE":
            print(f"   scope真话: {str(hy.get('scope_note'))[:110]}")
    n = len(CASES)
    print(f"\n== 汇总：词法 {lex_ok}/{n}，混合(含SCOPE真话) {hyb_ok}/{n}，耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
