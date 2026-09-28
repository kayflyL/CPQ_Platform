"""默认导出模板(id=1) L6 明细区改绑区域聚合字段（2026-09-15，幂等）。

L6 明细本无逐行价格（价格在整机级），逐行绑定只会写空白；改绑 scope=region
聚合字段后，填充器把整机单台价写在区域首行并按实际行数纵向合并（合并单元格）。

l6_details fieldMapping：
  移除 final_price→E / base_price→F / profit_margin→G（逐行）
  写入 l6_sell_price→E / l6_base_price→F / l6_margin_rate→G（整机聚合）

原模板 JSON 已有备份（backup_univer_tpl1_20260915.json），此处不再重复备份。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.univer_template_repo import UniverTemplateRepo

TEMPLATE_ID = 1

REMOVE = {"final_price", "base_price", "profit_margin"}
ADD = {"l6_sell_price": "E", "l6_base_price": "F", "l6_margin_rate": "G"}


def main() -> int:
    repo = UniverTemplateRepo()
    t = repo.get_by_id(TEMPLATE_ID)
    if not t:
        print(f"❌ 模板 {TEMPLATE_ID} 不存在")
        return 1

    bindings = t["bindings"]
    changed = []
    for b in bindings:
        region = b.get("regionFieldKey") or (b.get("fieldKey") if b.get("dataType") == "dynamic" else None)
        if region != "l6_details":
            continue
        fm = b.setdefault("fieldMapping", {})
        for field in REMOVE:
            if field in fm:
                del fm[field]
                changed.append(f"l6_details 移除 {field}→? ({b.get('sheetId')})")
        for field, col in ADD.items():
            if fm.get(field) != col:
                fm[field] = col
                changed.append(f"l6_details {field}→{col} ({b.get('sheetId')})")

    if not changed:
        print("✅ 无需变更（已是目标状态）")
        return 0

    repo.update(TEMPLATE_ID, {"bindings": bindings})
    print(f"✅ 模板 {TEMPLATE_ID} 已更新 {len(changed)} 处：")
    for c in changed:
        print("   -", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
