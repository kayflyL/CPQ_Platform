"""默认导出模板(id=1) 价格列总价口径改绑 + 维保费绑定 + 锚点居中（2026-09-15，幂等）。

背景（用户三点反馈）：
  1. 四种价格目录化：单价/总价 × 成本/销售 均可绑定；
  2. Quotation 列改绑销售总价，使列上 L6+KP+维保 与 Total Price（cfg_unit_price）堆叠闭合；
  3. 编辑器旧页面保存曾把聚合绑定覆盖回逐行绑定（合并失效的根因），本脚本恢复并加固。

动作（幂等）：
  A. l6_details：移除逐行价格绑定，改绑聚合字段 E/F/G = l6_sell_price/l6_base_price/l6_margin_rate
  B. kp_details：E final_price→sell_total；F base_price→cost_total（G profit_margin 不动）
  C. 静态绑定补：sheet-2 E23=cfg_warranty_l6、E24=cfg_warranty_kp（维保两行，插行自动下移）
  D. L6 锚点格（sheet-2 r6 E/F/G）样式克隆现有 + 垂直居中（vt=2），合并格内容默认居中

原模板备份已有（backup_univer_tpl1_20260915.json）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.univer_template_repo import UniverTemplateRepo

TEMPLATE_ID = 1

L6_REMOVE = {"final_price", "base_price", "profit_margin"}
L6_ADD = {"l6_sell_price": "E", "l6_base_price": "F", "l6_margin_rate": "G"}
KP_SWAP = {"final_price": "sell_total", "base_price": "cost_total"}

WARRANTY_BINDINGS = [
    {"dataType": "static", "sheetId": "sheet-2", "cellAddress": "E23", "fieldKey": "cfg_warranty_l6"},
    {"dataType": "static", "sheetId": "sheet-2", "cellAddress": "E24", "fieldKey": "cfg_warranty_kp"},
]

ANCHOR_ROW = "5"  # sheet-2 r6 = L6 数据首行（锚点）
ANCHOR_COLS = ["4", "5", "6"]


def main() -> int:
    repo = UniverTemplateRepo()
    t = repo.get_by_id(TEMPLATE_ID)
    if not t:
        print(f"❌ 模板 {TEMPLATE_ID} 不存在")
        return 1

    snap = t["workbook_snapshot"]
    bindings = t["bindings"]
    changed = []

    # A/B. 区域绑定改绑
    for b in bindings:
        region = b.get("regionFieldKey") or (b.get("fieldKey") if b.get("dataType") == "dynamic" else None)
        if region == "l6_details":
            fm = b.setdefault("fieldMapping", {})
            for field in L6_REMOVE:
                if field in fm:
                    del fm[field]
                    changed.append(f"l6_details 移除 {field}")
            for field, col in L6_ADD.items():
                if fm.get(field) != col:
                    fm[field] = col
                    changed.append(f"l6_details {field}→{col}")
        elif region == "kp_details":
            fm = b.setdefault("fieldMapping", {})
            for old, new in KP_SWAP.items():
                col = fm.get(old)
                if col:
                    del fm[old]
                    fm[new] = col
                    changed.append(f"kp_details {old}→{new}（{col}）")

    # C. 维保行静态绑定
    for wb in WARRANTY_BINDINGS:
        exists = any(
            b.get("dataType") == "static"
            and b.get("sheetId") == wb["sheetId"]
            and b.get("cellAddress") == wb["cellAddress"]
            and b.get("fieldKey") == wb["fieldKey"]
            for b in bindings
        )
        if not exists:
            bindings.append(dict(wb))
            changed.append(f"静态绑定 {wb['cellAddress']}={wb['fieldKey']}")

    # D. 锚点居中样式（新建样式，不污染共享样式）
    styles = snap.setdefault("styles", {})
    sheet2 = snap["sheets"]["sheet-2"]
    anchor_row = sheet2.setdefault("cellData", {}).setdefault(ANCHOR_ROW, {})
    for col in ANCHOR_COLS:
        cell = anchor_row.setdefault(col, {})
        sid = cell.get("s")
        src = styles.get(sid) if sid else None
        if not src:
            continue
        centered = dict(src)
        centered["vt"] = 2  # VerticalAlign.MIDDLE
        # 已有居中克隆则复用
        new_sid = None
        for k, v in styles.items():
            if v == centered:
                new_sid = k
                break
        if new_sid is None:
            new_sid = f"aggC{col}"
            while new_sid in styles:
                new_sid += "x"
            styles[new_sid] = centered
        if cell.get("s") != new_sid:
            cell["s"] = new_sid
            changed.append(f"锚点 r6 {chr(65 + int(col))} 垂直居中（{new_sid}）")

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
