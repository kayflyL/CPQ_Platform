"""D1 补录：把商机结果与复盘 5 字段注册进 business_fields（现有库）。

init_business_fields.py 只在空表时播种；已有数据的库需跑此脚本补录，
否则 /api/opportunities/field-history/{industry|customer_type} 会因字段未注册而 400。

幂等：按 key 去重，已存在则跳过。配合 migrations/add_opportunity_result_fields.sql（加物理列）。

用法（backend 目录）：python -X utf8 scripts/seed_opportunity_result_fields.py
"""
import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sqlalchemy.orm import Session
from app.models.base import kp_engine
from app.models.business_field import BusinessField


FIELDS = [
    {"key": "industry", "label": "行业", "category": "opportunity", "source": "Opportunity", "source_column": "industry", "sort_order": 33},
    {"key": "customer_type", "label": "客户类型", "category": "opportunity", "source": "Opportunity", "source_column": "customer_type", "sort_order": 34},
    {"key": "result", "label": "业务结果", "category": "opportunity", "source": "Opportunity", "source_column": "result", "sort_order": 35},
    {"key": "win_reason", "label": "中标原因", "category": "opportunity", "source": "Opportunity", "source_column": "win_reason", "sort_order": 36},
    {"key": "lost_reason", "label": "丢标原因", "category": "opportunity", "source": "Opportunity", "source_column": "lost_reason", "sort_order": 37},
]


def main():
    session = Session(kp_engine)
    try:
        existing = {f.key for f in session.query(BusinessField).all()}
        added, skipped = [], []
        for d in FIELDS:
            if d["key"] in existing:
                skipped.append(d["key"])
                continue
            session.add(BusinessField(**d))
            added.append(d["key"])
        session.commit()
        print(f"✓ 新增 business_fields：{added or '无'}")
        print(f"  跳过（已存在）：{skipped or '无'}")
    finally:
        session.close()


if __name__ == '__main__':
    main()
