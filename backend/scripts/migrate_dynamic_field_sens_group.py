"""dynamic_source_fields 加 sens_group 敏感分组列 + 存量价格字段打标（2026-09-15，幂等）。

背景：报价工作台预览/导出支持按勾选揭示明细价格——明细销售价(sell)/成本价(cost)/利润率(margin)。
分组不硬编码在导出链路，而是作为字段目录(rules.dynamic_source_fields)的一等属性：
模板编辑器显示徽标、预览端点按 reveal+权限掩蔽未揭示列（整列隐藏，不写值）。

动作（幂等，可重复执行）：
  A. ALTER TABLE rules.dynamic_source_fields ADD COLUMN IF NOT EXISTS sens_group TEXT
  B. 存量打标（只认 source_key+field_key，已带 sens_group 的不覆盖）：
     kp_details / l6_details 的 base_price→cost、final_price→sell、profit_margin→margin
  C. config_summary 补 margin 行（综合利润率%，sens_group=margin）——loader 已产出该字段
"""
import sys

import sqlalchemy as sa
from _localdb import db_url

ENG = sa.create_engine(
    db_url(),
    connect_args={"client_encoding": "UTF8"},
)

TAGS = [
    ("kp_details", "base_price", "cost"),
    ("kp_details", "final_price", "sell"),
    ("kp_details", "profit_margin", "margin"),
    ("l6_details", "base_price", "cost"),
    ("l6_details", "final_price", "sell"),
    ("l6_details", "profit_margin", "margin"),
]


def main() -> int:
    with ENG.begin() as c:
        c.execute(sa.text(
            "ALTER TABLE rules.dynamic_source_fields ADD COLUMN IF NOT EXISTS sens_group TEXT"
        ))

    tagged = 0
    with ENG.begin() as c:
        for source_key, field_key, group in TAGS:
            res = c.execute(sa.text("""
                UPDATE rules.dynamic_source_fields
                SET sens_group = :g
                WHERE source_key = :s AND field_key = :f
                  AND (sens_group IS NULL OR sens_group <> :g)
            """), {"g": group, "s": source_key, "f": field_key})
            tagged += res.rowcount or 0

    # config_summary.margin（综合利润率）缺失则补
    inserted = 0
    with ENG.begin() as c:
        exists = c.execute(sa.text("""
            SELECT 1 FROM rules.dynamic_source_fields
            WHERE source_key = 'config_summary' AND field_key = 'margin'
        """)).first()
        if not exists:
            c.execute(sa.text("""
                INSERT INTO rules.dynamic_source_fields (source_key, field_key, field_label, sort_order, enabled, sens_group)
                VALUES ('config_summary', 'margin', '综合利润率', 60, TRUE, 'margin')
            """))
            inserted = 1

    print(f"✅ sens_group 列就绪；打标 {tagged} 行；补 config_summary.margin {inserted} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
