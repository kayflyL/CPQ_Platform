"""一次性修复：存量 baseline 解决方案的适配平台从虚构型号刷成真实机型绑定。

种子（solution_seed._SEED）按 key 幂等、绝不覆盖已有行，因此 DB 里带虚构型号
（Orion ES22V3 / Titan TS33V2…，link=/strategies/selection）的存量行不会被种子更新。
本脚本从 _SEED 取权威内容，只刷 platforms 列；幂等护栏：行内任一平台已带 model_id
（视为已人工整理过）则整行跳过。运行前把旧值备份到同目录 _backup_solutions_platforms_*.json。

用法：python -X utf8 backend/scripts/fix_solution_platforms.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.base import Rules_SessionLocal
from app.models.solution import Solution
from app.services.solution_seed import _SEED


def main() -> int:
    s = Rules_SessionLocal()
    try:
        rows = s.query(Solution).filter(Solution.key.in_([item["key"] for item in _SEED])).all()
        targets = []
        for row in rows:
            platforms = json.loads(row.platforms) if row.platforms else []
            if any(p.get("model_id") for p in platforms):
                continue  # 已绑真实机型，尊重现状
            targets.append(row)
        if not targets:
            print("nothing to fix: all baseline solutions already bound to real models")
            return 0

        backup_path = ROOT / "scripts" / f"_backup_solutions_platforms_{date.today():%Y%m%d}.json"
        backup = {r.key: (json.loads(r.platforms) if r.platforms else []) for r in targets}
        backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"backed up {len(backup)} rows -> {backup_path.name}")

        seed_by_key = {item["key"]: item["platforms"] for item in _SEED}
        for row in targets:
            row.platforms = json.dumps(seed_by_key[row.key], ensure_ascii=False)
            print(f"fixed {row.key}: {[p['name'] for p in seed_by_key[row.key]]}")
        s.commit()
        print(f"done: {len(targets)} rows updated")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    raise SystemExit(main())
