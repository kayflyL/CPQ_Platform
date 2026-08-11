# -*- coding: utf-8 -*-
"""回填 2026-08-06 后录入、缺 specs 的 KP 配件规格。

13 件(硬盘/内存/网卡/RAID)从 name 确定性解析，3 件 GPU 用联网查得的规格。
默认 dry-run 逐件打印将写入的 specs；加 --commit 才真写库(update_part 全量替换，
目标件当前 0 specs，替换=纯新增)。

跑法（backend 目录）：
  ./.venv/Scripts/python.exe -X utf8 scripts/backfill_missing_specs.py            # dry-run
  ./.venv/Scripts/python.exe -X utf8 scripts/backfill_missing_specs.py --commit    # 写库
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.models.kp import KPPart
from app.repository.kp_repo import (
    KPRepository,
    _icap, _itype, _imedia, _iform, _irpm,
    _imem_type, _imem_speed, _imem_dimm, _imem_rank, _imem_ecc,
)

# GPU 规格（WebSearch 联网查得，字段口径参照库里已有 GPU 件如 RTX5090）。
# CUDA Cores 仅 NVIDIA 填；AMD 用 Stream Processors(不套 NVIDIA 字段)、国产卡 Boost/CUDA 未公开→留空。
GPU_SPECS = {
    280: {  # NVIDIA RTX Pro6000 96G (Blackwell Workstation)
        "Capacity": "96 GB", "tdp": "600", "Architecture": "Blackwell",
        "Memory Bandwidth": "1792 GB/s", "Memory Interface": "512-bit",
        "Interface": "PCIe Gen 5", "Form Factor": "2-Slot", "Cooling": "Active",
        "CUDA Cores": "24064", "Boost Clock": "2.617 GHz", "MSRP": "8565 USD",
    },
    274: {  # AMD Radeon AI PRO R9700 32G (RDNA 4)
        "Capacity": "32 GB", "tdp": "260", "Architecture": "RDNA 4",
        "Memory Bandwidth": "640 GB/s", "Memory Interface": "256-bit",
        "Interface": "PCIe Gen 5", "Form Factor": "2-Slot", "Cooling": "Active",
        "Boost Clock": "2.92 GHz", "MSRP": "1299 USD",
    },
    270: {  # 天数智芯 天垓150 (BI-V150) — HBM2e
        "Capacity": "64 GB", "tdp": "350", "Architecture": "通用GPU(SIMT,7nm)",
        "Memory Bandwidth": "800 GB/s", "Interface": "PCIe Gen 4",
    },
}


def specs_hdd(name):
    out = {}
    cap, typ, med = _icap(name), _itype(name), _imedia(name)
    if cap: out["Capacity"] = cap
    if typ: out["Type"] = typ
    if med: out["Media"] = med
    ff = _iform(name)
    if not ff:  # name 未写形态→按 Type/Media 默认推断(与库里 NVMe→U.2 一致)
        if typ == "NVMe": ff = "U.2"
        elif med == "SSD": ff = '2.5"'
        elif med == "HDD": ff = '3.5"'
    if ff: out["Form Factor"] = ff
    rpm = _irpm(name)
    if rpm: out["RPM"] = rpm
    return out


def specs_mem(name):
    out = {}
    for k, f in [("Capacity", _icap), ("Type", _imem_type), ("Speed", _imem_speed),
                 ("DIMM Type", _imem_dimm), ("Rank", _imem_rank), ("ECC", _imem_ecc)]:
        v = f(name)
        if v: out[k] = v
    return out


def specs_nic(name):
    out = {}
    raw = name.upper()                       # 保留空格，避免 CX4 与 2Port 粘连成 CX42
    compact = raw.replace(" ", "")
    if "双口" in name or "2PORT" in compact:
        out["Ports"] = "2"
    else:
        m = re.search(r"(\d+)\s*PORT", raw)
        if m: out["Ports"] = m.group(1)
    m = re.search(r"(\d+)G\b", raw)          # 词边界，防吞 2Port 的 2
    if m: out["Link Speed"] = m.group(1) + "G"
    m = re.search(r"(CX\d+|I\d+|X\d+)", raw)   # raw 带空格，\d+ 不跨空格吞字符，无需 \b
    if m: out["接口"] = m.group(1)
    return out


def specs_raid(name):
    out = {}
    u = name.upper()
    m = re.search(r"(\d+)\s*G\s*CACHE", u)
    if m: out["Cache"] = m.group(1) + " GB"
    if "SUPERCAP" in u or "超级电容" in name or "电容" in name:
        out["电容"] = "有"
    m = re.search(r"-(\d+)I\b", u)
    if m: out["Ports"] = m.group(1)
    return out


CAT_PARSE = {
    "HDD/SSD": specs_hdd,
    "Memory": specs_mem,
    "Network(NIC) requirement": specs_nic,
    "Raid card": specs_raid,
    "Raid Card": specs_raid,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="实际写库(默认 dry-run)")
    args = ap.parse_args()

    repo = KPRepository()
    try:
        parts = repo.session.query(KPPart)\
            .filter(KPPart.created_at >= datetime(2026, 8, 6))\
            .order_by(KPPart.created_at).all()
        mode = "COMMIT 写库" if args.commit else "DRY-RUN(不写库)"
        print(f"=== {mode}: {len(parts)} 件 ===")
        for p in parts:
            cat = p.category.name if p.category else "?"
            if cat in ("GPU", "GPU card"):
                specs = dict(GPU_SPECS.get(p.id, {}))
                src = "GPU联网"
            else:
                specs = CAT_PARSE.get(cat, lambda n: {})(p.name)
                src = "name解析"
            print(f"[{cat}] id={p.id} {p.name}  ({src}, {len(specs)}条)")
            print(f"    -> {specs}")
            if args.commit and specs:
                repo.update_part(p.id, {"specs": [{"key": k, "value": v} for k, v in specs.items()]})
        print("\n✅ 已写库" if args.commit else "\n(dry-run，加 --commit 写库)")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
