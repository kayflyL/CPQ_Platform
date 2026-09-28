"""dynamic_source_fields 加 scope 作用域列 + L6 区域聚合字段（2026-09-15，幂等）。

背景：L6 明细本无逐行价格，价格在整机级。新增「区域聚合字段」机制：
scope=row(默认)=逐行明细；scope=region=整机一个值，填充器把值写在区域首行
并按实际行数运行时生成纵向 mergeData（合并单元格），模板无需预画合并。

同时 l6_details 域补 3 个聚合字段（与 config_summary 同口径，单台价）：
  l6_sell_price  整机售价  sens=sell
  l6_base_price  整机成本  sens=cost
  l6_margin_rate 整机利润率 sens=margin

动作（幂等，可重复执行）：
  A. ALTER TABLE rules.dynamic_source_fields ADD COLUMN IF NOT EXISTS scope TEXT
  B. INSERT 3 行聚合字段（ON CONFLICT 语义用先查后插）
"""
import sys

import sqlalchemy as sa
from _localdb import db_url

ENG = sa.create_engine(
    db_url(),
    connect_args={"client_encoding": "UTF8"},
)

AGG_FIELDS = [
    # (source_key, field_key, label, sort, sens_group)
    ("l6_details", "l6_sell_price", "整机售价", 55, "sell"),
    ("l6_details", "l6_base_price", "整机成本", 56, "cost"),
    ("l6_details", "l6_margin_rate", "整机利润率", 57, "margin"),
]


def main() -> int:
    with ENG.begin() as c:
        c.execute(sa.text(
            "ALTER TABLE rules.dynamic_source_fields ADD COLUMN IF NOT EXISTS scope TEXT"
        ))

    inserted = 0
    with ENG.begin() as c:
        for source_key, field_key, label, sort, sens in AGG_FIELDS:
            exists = c.execute(sa.text("""
                SELECT 1 FROM rules.dynamic_source_fields
                WHERE source_key = :s AND field_key = :f
            """), {"s": source_key, "f": field_key}).first()
            if not exists:
                c.execute(sa.text("""
                    INSERT INTO rules.dynamic_source_fields
                        (source_key, field_key, field_label, sort_order, enabled, sens_group, scope)
                    VALUES (:s, :f, :l, :o, TRUE, :g, 'region')
                """), {"s": source_key, "f": field_key, "l": label, "o": sort, "g": sens})
                inserted += 1

    print(f"✅ scope 列就绪；补聚合字段 {inserted} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
