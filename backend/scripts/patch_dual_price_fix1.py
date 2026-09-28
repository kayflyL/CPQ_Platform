"""模板1 修复 follow-up（2026-09-15）：
1. E13 残留标记 '{{含税单价}}' 迁到 F13（五列手术后绑定已移 F13，标记格漏移 → 导出残留文字）
2. Warranty 横幅合并 A..G 拉通到 A..I（与 L6/Keypats 横幅一致）
幂等：重复执行无副作用。
"""
import copy
import json
import sys

import sqlalchemy as sa

sys.path.insert(0, ".")
from scripts._localdb import db_url

ENG = sa.create_engine(db_url(), connect_args={"client_encoding": "UTF8"})


def main() -> int:
    with ENG.connect() as c:
        row = c.execute(sa.text(
            "SELECT workbook_snapshot FROM opportunities.univer_templates WHERE id = 1"
        )).fetchone()
    snap = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    sheet = snap["sheets"]["sheet-2"]
    cd = sheet["cellData"]

    # 1) 标记迁移 E13(idx12,col4) → F13(idx12,col5)
    moved = False
    row13 = cd.get("12") or {}
    e13 = row13.get("4")
    if e13 is not None and isinstance(e13.get("v"), str) and "含税单价" in e13["v"]:
        f13 = copy.deepcopy(e13)
        row13["5"] = f13
        del row13["4"]
        moved = True

    # 2) Warranty 横幅（startRow=9, startColumn=0）endColumn 拉通到 8
    banner_fixed = 0
    for m in sheet.get("mergeData", []):
        if m.get("startRow") == 9 and m.get("startColumn") == 0 and m.get("endColumn", 0) < 8:
            m["endColumn"] = 8
            banner_fixed += 1

    with ENG.begin() as c:
        c.execute(sa.text("""
            UPDATE opportunities.univer_templates
            SET workbook_snapshot = CAST(:snap AS jsonb), updated_at = now()
            WHERE id = 1
        """), {"snap": json.dumps(snap, ensure_ascii=False)})

    print(f"✅ 标记迁移 E13→F13: {'done' if moved else 'skip(已修)'}；Warranty 横幅拉通: {banner_fixed} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
