"""默认导出模板(id=1 正式报价单)绑定价格敏感列（2026-09-15，幂等）。

配合 sens_group 机制：字段先在 rules.dynamic_source_fields 打标（见
migrate_dynamic_field_sens_group.py），模板这边把明细区域的价格字段绑到具体列，
预览端点按 reveal+权限对未揭示列整列隐藏——列显示 = 模板绑定 × 导出选项。

绑定布局（沿用既有表头设计，样式从同区既有单元格复制）：
  sheet-1 封面 · config_summary 区（表头 r5，数据 r6）：
      G 列 = 综合利润率（margin，对内）
  sheet-2 配置页 · L6 区（表头 r5，数据 r6）：
      E=Quotation(已有表头) → 售价 final_price
      F=Note → 改表头 Cost → 成本 base_price（Note 列从未绑定，腾出来用）
      G=新增 Margin % → 利润率 profit_margin
  sheet-2 配置页 · KP 区（表头 r8，数据 r9）：
      D=补表头 Qty（数据早已绑 D，表头一直缺）
      E=Quotation / F=Cost / G=Margin %（表头新增，样式复制 E 列既有样式）

执行前把原模板 JSON 备份到 scripts/backup_univer_tpl1_20260915.json。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.univer_template_repo import UniverTemplateRepo

TEMPLATE_ID = 1
BACKUP = Path(__file__).parent / "backup_univer_tpl1_20260915.json"

# (sheet_id, 行idx, 列idx, 表头文字, 样式来源列idx)
HEADER_PATCH = [
    ("sheet-1", 4, 6, "综合利润率", 5),          # 封面 r5 G：复制 F(含税总价) 样式
    ("sheet-2", 4, 5, "Cost", 4),                # L6 r5 F：Note→Cost（已有样式不动，只改字）
    ("sheet-2", 4, 6, "Margin %", 4),            # L6 r5 G：复制 E(Quotation) 样式
    ("sheet-2", 7, 3, "Qty", 2),                 # KP r8 D：补 Qty 表头
    ("sheet-2", 7, 4, "Quotation", 2),           # KP r8 E
    ("sheet-2", 7, 5, "Cost", 2),                # KP r8 F
    ("sheet-2", 7, 6, "Margin %", 2),            # KP r8 G
]

# (sheet_id, 模板行idx, 列idx, 样式来源列idx)：数据模板行补带样式的空单元格
DATA_ROW_PATCH = [
    ("sheet-1", 5, 6, 5),   # 封面 r6 G（已有 hNsJtm 样式则跳过）
    ("sheet-2", 5, 6, 4),   # L6 r6 G
    ("sheet-2", 8, 6, 4),   # KP r9 G
]

# 区域 fieldMapping 追加
MAPPING_PATCH = {
    "config_summary": {"margin": "G"},
    "l6_details": {"final_price": "E", "base_price": "F", "profit_margin": "G"},
    "kp_details": {"final_price": "E", "base_price": "F", "profit_margin": "G"},
}

# 新列补宽度（沿用该 sheet E 列宽度量级）
WIDTH_PATCH = {
    ("sheet-2", "5"): 83.69,
    ("sheet-2", "6"): 83.69,
    ("sheet-1", "6"): 96.21,
}


def main() -> int:
    repo = UniverTemplateRepo()
    t = repo.get_by_id(TEMPLATE_ID)
    if not t:
        print(f"❌ 模板 {TEMPLATE_ID} 不存在")
        return 1

    if not BACKUP.exists():
        BACKUP.write_text(json.dumps(
            {"workbook_snapshot": t["workbook_snapshot"], "bindings": t["bindings"]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✅ 已备份原模板 → {BACKUP.name}")
    else:
        print(f"ℹ️ 备份已存在，跳过（{BACKUP.name}）")

    snap = t["workbook_snapshot"]
    bindings = t["bindings"]
    changed = []

    for sid, row, col, text, style_from in HEADER_PATCH:
        cell = snap["sheets"][sid].setdefault("cellData", {}).setdefault(str(row), {})
        key = str(col)
        if cell.get(key, {}).get("v") == text:
            continue
        src = snap["sheets"][sid]["cellData"].get(str(row), {}).get(str(style_from), {})
        new_cell = dict(cell.get(key) or {})
        if new_cell.get("v") in (None, "", "Note") or "v" not in new_cell:
            new_cell["v"] = text
        if "s" not in new_cell and src.get("s"):
            new_cell["s"] = src["s"]
        cell[key] = new_cell
        changed.append(f"{sid} r{row + 1}{chr(65 + col)}={text!r}")

    for sid, row, col, style_from in DATA_ROW_PATCH:
        cell = snap["sheets"][sid].setdefault("cellData", {}).setdefault(str(row), {})
        key = str(col)
        if key in cell and cell[key].get("s"):
            continue
        src = snap["sheets"][sid]["cellData"].get(str(row), {}).get(str(style_from), {})
        new_cell = {"v": ""}
        if src.get("s"):
            new_cell["s"] = src["s"]
        cell[key] = new_cell
        changed.append(f"{sid} r{row + 1}{chr(65 + col)} 补样式")

    for (sid, col), w in WIDTH_PATCH.items():
        cd = snap["sheets"][sid].setdefault("columnData", {})
        if "w" not in (cd.get(col) or {}):
            cd[col] = {"w": w}
            changed.append(f"{sid} col{col} 宽 {w}")

    for b in bindings:
        region = b.get("regionFieldKey") or (b.get("fieldKey") if b.get("dataType") == "dynamic" else None)
        if region in MAPPING_PATCH:
            fm = b.setdefault("fieldMapping", {})
            for field, col_letter in MAPPING_PATCH[region].items():
                if fm.get(field) != col_letter:
                    fm[field] = col_letter
                    changed.append(f"{region}.{field}→{col_letter} ({b.get('sheetId')})")

    if not changed:
        print("✅ 无需变更（已是目标状态）")
        return 0

    repo.update(TEMPLATE_ID, {"workbook_snapshot": snap, "bindings": bindings})
    print(f"✅ 模板 {TEMPLATE_ID} 已更新 {len(changed)} 处：")
    for c in changed:
        print("   -", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
