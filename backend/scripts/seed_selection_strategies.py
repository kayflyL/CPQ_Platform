"""C1 — 策略中心：选型硬规则种子（selection.conflict / selection.require）。

凭服务器行业经验列高价值硬规则（不依赖配件 specs 齐全）：
- conflict：同配置内互斥（电源/内存/CPU 不混型号）
- require：有 A 必有 B（NVMe 盘→NVMe 背板，SAS/SATA→HBA/RAID）

body schema：
  conflict: {"check":"unique","where":{"part_category":X},"by":"catalogue","desc":"..."}
    → 同一配置内，part_category=X 的件，catalogue 必须唯一（防混型号）
  require:  {"if":{"part_category":X,"specs.k":v},"need":{"part_category":Y},"desc":"..."}
    → 若配置内有满足 if 的件，则必须也有满足 need 的件

status=active（生效）；scope=null（通用）。幂等：同 type+name 已存在则跳过。
part_category 值若与料号库实际不符，C2 校验时再校准。

用法（backend 目录）：python -X utf8 scripts/seed_selection_strategies.py
"""
import sys
import os
import json

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.repository.strategy_repo import StrategyRepository


CONFLICTS = [
    {"name": "电源同型号不混搭",
     "where": {"part_category": "PSU"}, "by": "catalogue",
     "desc": "电源 PSU 必须同型号，禁止混搭不同功率/型号"},
    {"name": "内存同型号不混搭",
     "where": {"part_category": "Memory"}, "by": "catalogue",
     "desc": "内存必须同型号同速率；禁止 RDIMM/LRDIMM 或不同速率混用"},
    {"name": "CPU 双路同型号",
     "where": {"part_category": "CPU"}, "by": "catalogue",
     "desc": "双路 CPU 必须同型号"},
]

REQUIRES = [
    {"name": "NVMe 盘需配 NVMe 背板",
     "if": {"part_category": "硬盘", "specs.interface": "NVMe"},
     "need": {"part_category": "背板", "specs.support": "tri-mode"},
     "desc": "选了 NVMe 硬盘，必须配支持 NVMe 的 tri-mode 背板"},
    {"name": "SAS/SATA 盘需配 HBA/RAID",
     "if": {"part_category": "硬盘", "specs.interface": ["SAS", "SATA"]},
     "need": {"part_category": ["HBA", "RAID"]},
     "desc": "选了 SAS/SATA 硬盘，必须配 HBA 或 RAID 卡"},
]


def main():
    repo = StrategyRepository()
    try:
        existing = {(s["type"], s["name"]) for s in repo.list(domain="selection")}
        added, skipped = [], []

        for c in CONFLICTS:
            if ("conflict", c["name"]) in existing:
                skipped.append(c["name"])
                continue
            repo.create({
                "domain": "selection", "type": "conflict", "name": c["name"],
                "body": {"check": "unique", "where": c["where"], "by": c["by"], "desc": c["desc"]},
                "status": "active",
                "description": c["desc"], "change_reason": "一期种子",
            }, operator="seed")
            added.append("conflict:" + c["name"])

        for r in REQUIRES:
            if ("require", r["name"]) in existing:
                skipped.append(r["name"])
                continue
            repo.create({
                "domain": "selection", "type": "require", "name": r["name"],
                "body": {"if": r["if"], "need": r["need"], "desc": r["desc"]},
                "status": "active",
                "description": r["desc"], "change_reason": "一期种子",
            }, operator="seed")
            added.append("require:" + r["name"])

        print(f"✓ 新增选型规则：{added or '无'}")
        print(f"  跳过（已存在）：{skipped or '无'}")
    finally:
        repo.close()


if __name__ == '__main__':
    main()
