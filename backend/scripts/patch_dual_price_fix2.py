"""模板1 修复 follow-up 2（2026-09-15）：
头部信息 Sales/FAE/DATE 值格被五列手术机械推到 G 列（Unit Cost）——
客户版 cost 未勾时 G/H/I 整列隐藏，值陪葬；勾了成本价显示出来也和 E 标签隔一个空 F。
迁回 F 列（销售总价列，任何揭示档位都不隐藏，静态绑定无 sens_group 不参与掩蔽）。
幂等：重复执行无副作用。
"""
import copy
import json
import sys

import sqlalchemy as sa

sys.path.insert(0, ".")
from scripts._localdb import db_url

ENG = sa.create_engine(db_url(), connect_args={"client_encoding": "UTF8"})

MOVE = {0: "G1->F1", 1: "G2->F2", 2: "G3->F3"}  # 0-indexed row
ADDR_REMAP = {"G1": "F1", "G2": "F2", "G3": "F3"}


def main() -> int:
    with ENG.connect() as c:
        row = c.execute(sa.text(
            "SELECT workbook_snapshot, bindings FROM opportunities.univer_templates WHERE id = 1"
        )).fetchone()
    snap = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    binds = row[1] if isinstance(row[1], list) else json.loads(row[1])
    sheet = snap["sheets"]["sheet-2"]
    cd = sheet["cellData"]

    moved = []
    for ridx in MOVE:
        rowd = cd.get(str(ridx)) or {}
        g = rowd.get("6")
        if g is not None and "5" not in rowd:
            rowd["5"] = copy.deepcopy(g)
            del rowd["6"]
            moved.append(MOVE[ridx])
        # 残留旧行值再清一次（值格在 G 但 F 已有内容→只删 G）
        elif g is not None and "5" in rowd:
            del rowd["6"]
            moved.append(MOVE[ridx] + "(清残留)")

    remapped = []
    for b in binds:
        if b.get("sheetId") == "sheet-2" and b.get("dataType") == "static":
            old = b.get("cellAddress")
            new = ADDR_REMAP.get(old)
            if new:
                b["cellAddress"] = new
                remapped.append(f"{old}->{new} {b.get('fieldKey')}")

    with ENG.begin() as c:
        c.execute(sa.text("""
            UPDATE opportunities.univer_templates
            SET workbook_snapshot = CAST(:snap AS jsonb), bindings = CAST(:b AS jsonb),
                updated_at = now()
            WHERE id = 1
        """), {"snap": json.dumps(snap, ensure_ascii=False),
               "b": json.dumps(binds, ensure_ascii=False)})

    print(f"✅ 值格迁移: {moved or 'skip(已修)'}；绑定重排: {remapped or 'skip(已修)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
