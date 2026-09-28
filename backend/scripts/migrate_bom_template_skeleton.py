# -*- coding: utf-8 -*-
"""BOM 模板瘦身迁移（2026-09-15 类型驱动重构）：
rows 里的逐行 rule DSL 已收进行类型固定属性（前端 bomRuleEngine.TYPE_RULES /
后端 bom_template_eval._TYPE_RULES），模板只留骨架 type/label/slot/mode。
本脚本把存量 rows 里的 rule 键剥掉；幂等（无 rule 可剥即跳过）。
跑前自检：未知行类型打 WARNING（引擎会回落 manual 留空手填，不丢行）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _localdb import db_url  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

KNOWN_TYPES = {
    "front_backplane", "io_slot", "rear_summary", "heatsink", "fan",
    "psu_requirement", "gpu_power_cord", "power_cord", "rail_kit",
    "cable", "raid_slot",
}
KEEP_KEYS = {"type", "label", "slot", "mode"}


def main() -> None:
    eng = create_engine(db_url(), connect_args={"client_encoding": "UTF8"})
    with eng.begin() as c:
        tpls = c.execute(text("SELECT id, name, rows FROM l6.bom_templates ORDER BY id")).mappings().all()
        for t in tpls:
            rows = t["rows"]
            if not isinstance(rows, list):
                print(f"[skip] #{t['id']} {t['name']}: rows 非 list")
                continue
            unknown = sorted({r.get("type") for r in rows if isinstance(r, dict)
                              and r.get("type") not in KNOWN_TYPES} - {None})
            if unknown:
                print(f"[WARN] #{t['id']} {t['name']}: 未知行类型 {unknown}（引擎回落 manual）")
            stripped = []
            changed = False
            for r in rows:
                if not isinstance(r, dict):
                    print(f"[WARN] #{t['id']} {t['name']}: 非法行 {r!r}，原样保留")
                    stripped.append(r)
                    continue
                slim = {k: v for k, v in r.items() if k in KEEP_KEYS}
                if set(slim.keys()) != set(r.keys()):
                    changed = True
                stripped.append(slim)
            if not changed:
                print(f"[ok] #{t['id']} {t['name']}: 已是骨架，跳过")
                continue
            c.execute(text("UPDATE l6.bom_templates SET rows=:rows WHERE id=:id"),
                      {"rows": json.dumps(stripped, ensure_ascii=False), "id": t["id"]})
            print(f"[done] #{t['id']} {t['name']}: {len(stripped)} 行已剥 rule → 骨架")


if __name__ == "__main__":
    main()
