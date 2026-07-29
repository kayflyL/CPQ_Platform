"""A1 — 策略中心：补 3 个商机 enum 字段（行业 / 客户类型 / 商机结果）。

走 BusinessField 体系（display_type=enum + options JSON），存 rules.business_fields。
options 后台可改（用户定调"后期可改"）；商机详情页信息栏会按 BusinessField 自动渲染。
is_core_field=False → 值进 opportunity.extra_fields JSON，不建真实列。

幂等：已存在的 key 跳过，不覆盖（改 options 请去管理后台 BusinessFieldManagement）。

用法（backend 目录）：python -X utf8 scripts/seed_strategy_fields.py
"""
import sys
import os
import json
from datetime import datetime

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.models.base import Rules_SessionLocal
from app.models.business_field import BusinessField


# 3 个市场维度字段；options 起步值（后台 BusinessFieldManagement 可改）
FIELDS = [
    {
        "key": "industry",
        "label": "行业",
        "options": ["AI算力", "IDC机房", "政企信息化", "高校科研", "安防存储", "工业边缘"],
        "sort_order": 100,
    },
    {
        "key": "customer_type",
        "label": "客户类型",
        "options": ["直签大客户", "渠道分销", "集采项目", "零散项目"],
        "sort_order": 101,
    },
    {
        "key": "opportunity_result",
        "label": "商机结果",
        "options": ["进行中", "中标", "失标", "搁置"],
        "sort_order": 102,
    },
]


def main():
    s = Rules_SessionLocal()
    try:
        now = datetime.now().isoformat()
        added, skipped = [], []
        for f in FIELDS:
            exist = s.query(BusinessField).filter(BusinessField.key == f["key"]).first()
            if exist:
                skipped.append(f["key"])
                continue
            s.add(BusinessField(
                key=f["key"],
                label=f["label"],
                category="opportunity",
                source="Opportunity",
                source_column=None,          # 存 extra_fields，非真实列
                type="text",
                display_type="enum",
                options=json.dumps(f["options"], ensure_ascii=False),
                group_name="市场维度",
                sort_order=f["sort_order"],
                is_core_field=False,
                used_in_pages=json.dumps(["opportunity_detail"], ensure_ascii=False),
                enabled=True,
                permission="editable",
                created_at=now,
                updated_at=now,
                created_by="strategy_center",
                updated_by="strategy_center",
            ))
            added.append(f["key"])
        s.commit()
        print(f"✓ 新增字段：{added or '无'}")
        print(f"  跳过（已存在）：{skipped or '无'}")
    finally:
        s.close()


if __name__ == '__main__':
    main()
