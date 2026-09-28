"""模板1 配置页明细表五列改造（2026-09-15，双列常显：销售单价/总价 + 成本单价/总价 + 利润率）。

sheet-2 布局：... | D Qty | E 销售单价 | F 销售总价 | G 成本单价 | H 成本总价 | I Margin %
绑定重排：KP 行 E=final_price F=sell_total G=base_price H=cost_total I=profit_margin；
L6 合并格 F=l6_sell_price H=l6_base_price I=l6_margin_rate（E/G 留空，整机无单价/总价之分）；
头部信息 F1/F2/F3→G1/G2/G3；Total Price 值 E13→F13（落销售总价列，堆叠闭合）；
维保费 E23/E24→F11/F12（归位到维保描述行旁，修模板坐标错位）。
"""
import copy
import json
import sys

import sqlalchemy as sa

sys.path.insert(0, ".")
from scripts._localdb import db_url

ENG = sa.create_engine(db_url(), connect_args={"client_encoding": "UTF8"})

SHEET = "sheet-2"
HDR_EN = "Unit Price"
HDR_F = "Total Price"
HDR_G = "Unit Cost"
HDR_H = "Cost Total"

STATIC_ADDR_REMAP = {  # 机械移位（F 块）+ 功能性迁移（Total/维保）
    "F1": "G1", "F2": "G2", "F3": "G3",
    "E13": "F13",
    "E23": "F11", "E24": "F12",
}
L6_DELTA = {"l6_sell_price": "F", "l6_base_price": "H", "l6_margin_rate": "I"}
KP_DELTA = {"final_price": "E", "sell_total": "F", "base_price": "G",
            "cost_total": "H", "profit_margin": "I"}
WARRANTY_MARKERS = {10: "{{cfg_warranty_l6}}", 11: "{{cfg_warranty_kp}}"}  # 0-indexed 行


def insert_col(sheet: dict, at: int):
    cd = sheet["cellData"]
    for row in cd.values():
        for cidx in sorted((int(k) for k in row if int(k) >= at), reverse=True):
            row[str(cidx + 1)] = row.pop(str(cidx))
    coldata = sheet.setdefault("columnData", {})
    for cidx in sorted((int(k) for k in coldata if int(k) >= at), reverse=True):
        coldata[str(cidx + 1)] = coldata.pop(str(cidx))
    src = coldata.get(str(at - 1)) or coldata.get(str(at)) or {}
    coldata[str(at)] = copy.deepcopy(src)
    for m in sheet.get("mergeData", []):
        if m.get("startColumn", 0) >= at:
            m["startColumn"] += 1
            m["endColumn"] += 1
        elif m.get("endColumn", 0) >= at:
            m["endColumn"] += 1


def surgery(snap: dict, binds: list) -> tuple[dict, list, list]:
    sheet = snap["sheets"][SHEET]
    cd = sheet["cellData"]

    # 1) 插列：E 后插 F、G 后插 H（净效果：E 留原地，旧 F→G，旧 G→I）
    insert_col(sheet, 5)
    insert_col(sheet, 7)

    # 2) 区块横幅（A4/A7 的 A..F 合并）拉通到全表宽 A..I
    for m in sheet.get("mergeData", []):
        if m.get("startColumn") == 0 and m.get("endColumn") == 6 and m.get("startRow") in (3, 6):
            m["endColumn"] = 8

    # 3) 表头文案（L6 表头 idx4 / KP 表头 idx7）
    for ridx in ("4", "7"):
        row = cd.setdefault(ridx, {})
        e = row.get("4")
        if e is None:
            raise RuntimeError(f"表头行 {ridx} 缺 E 列单元格")
        f = copy.deepcopy(e); f["v"] = HDR_F
        g = row.get("6")
        h = copy.deepcopy(g) if g is not None else {}
        h["v"] = HDR_H
        e["v"] = HDR_EN
        if g is not None:
            g["v"] = HDR_G
        row["5"] = f
        row["7"] = h

    # 4) 动态模板行（L6 idx5 / KP idx8）克隆新列样式
    for ridx in ("5", "8"):
        row = cd.get(ridx)
        if not row:
            continue
        for new_col, src_col in (("5", "4"), ("7", "6")):
            if new_col not in row and src_col in row:
                cell = copy.deepcopy(row[src_col])
                cell["v"] = ""
                row[new_col] = cell

    # 5) 维保费值格：F11/F12 克隆 E13（Total 值样式），删除旧 E23/E24 标记
    total_cell = copy.deepcopy(cd["12"]["4"])
    for ridx, marker in WARRANTY_MARKERS.items():
        cell = copy.deepcopy(total_cell)
        cell["v"] = marker
        cd.setdefault(str(ridx), {})["5"] = cell
    for ridx in ("22", "23"):
        row = cd.get(ridx)
        if row and "4" in row:
            del row["4"]

    # 6) 绑定重排
    changed = []
    for b in binds:
        if b.get("sheetId") != SHEET:
            continue
        if b.get("dataType") == "static":
            old = b.get("cellAddress")
            new = STATIC_ADDR_REMAP.get(old)
            if new:
                b["cellAddress"] = new
                changed.append(f"static {old}->{new} {b.get('fieldKey')}")
        elif b.get("dataType") == "dynamic":
            key = b.get("regionFieldKey") or b.get("fieldKey")
            delta = L6_DELTA if key == "l6_details" else KP_DELTA if key == "kp_details" else None
            if not delta:
                continue
            fm = dict(b.get("fieldMapping") or {})
            for k in L6_DELTA if key == "l6_details" else KP_DELTA:
                fm.pop(k, None)
            fm.update(delta)
            b["fieldMapping"] = fm
            changed.append(f"dynamic {key}: {delta}")
    return snap, binds, changed


def main() -> int:
    with ENG.begin() as c:
        c.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS opportunities.univer_templates_bak_dual_20260915 AS
            SELECT * FROM opportunities.univer_templates WHERE id = 1
        """))
        row = c.execute(sa.text(
            "SELECT workbook_snapshot, bindings FROM opportunities.univer_templates WHERE id = 1"
        )).fetchone()
    snap = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    binds = row[1] if isinstance(row[1], list) else json.loads(row[1])

    snap, binds, changed = surgery(snap, binds)

    with ENG.begin() as c:
        c.execute(sa.text("""
            UPDATE opportunities.univer_templates
            SET workbook_snapshot = CAST(:snap AS jsonb), bindings = CAST(:b AS jsonb),
                updated_at = now()
            WHERE id = 1
        """), {"snap": json.dumps(snap, ensure_ascii=False),
               "b": json.dumps(binds, ensure_ascii=False)})

    print(f"✅ 手术完成，备份表 opportunities.univer_templates_bak_dual_20260915")
    for line in changed:
        print("  -", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
