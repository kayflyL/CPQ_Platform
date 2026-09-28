"""dynamic_source_fields 补 KP 总价字段 + L6 聚合 label 更新（2026-09-15，幂等）。

四种价格口径目录化（可绑任意列，不硬编码）：
  kp_details.base_price  成本单价（已有）
  kp_details.cost_total  成本总价 = 单价×Qty（新增，sens=cost）
  kp_details.final_price 销售单价（已有）
  kp_details.sell_total  销售总价 = 单价×Qty（新增，sens=sell）
L6 聚合字段语义=整机口径总价，label 更清晰：
  整机售价→整机销售总价 / 整机成本→整机成本总价

Quotation 列（E）改绑 sell_total 后与 Total Price（cfg_unit_price）堆叠闭合。
"""
import sys

import sqlalchemy as sa
from _localdb import db_url

ENG = sa.create_engine(
    db_url(),
    connect_args={"client_encoding": "UTF8"},
)

NEW_FIELDS = [
    ("kp_details", "cost_total", "成本总价", 58, "cost"),
    ("kp_details", "sell_total", "销售总价", 59, "sell"),
]

LABEL_UPDATES = [
    ("l6_details", "l6_sell_price", "整机销售总价"),
    ("l6_details", "l6_base_price", "整机成本总价"),
]


def main() -> int:
    inserted = 0
    with ENG.begin() as c:
        for source_key, field_key, label, sort, sens in NEW_FIELDS:
            exists = c.execute(sa.text("""
                SELECT 1 FROM rules.dynamic_source_fields
                WHERE source_key = :s AND field_key = :f
            """), {"s": source_key, "f": field_key}).first()
            if not exists:
                c.execute(sa.text("""
                    INSERT INTO rules.dynamic_source_fields
                        (source_key, field_key, field_label, sort_order, enabled, sens_group, scope)
                    VALUES (:s, :f, :l, :o, TRUE, :g, 'row')
                """), {"s": source_key, "f": field_key, "l": label, "o": sort, "g": sens})
                inserted += 1

    relabeled = 0
    with ENG.begin() as c:
        for source_key, field_key, label in LABEL_UPDATES:
            res = c.execute(sa.text("""
                UPDATE rules.dynamic_source_fields
                SET field_label = :l
                WHERE source_key = :s AND field_key = :f AND field_label <> :l
            """), {"l": label, "s": source_key, "f": field_key})
            relabeled += res.rowcount or 0

    print(f"✅ 补总价字段 {inserted} 行；label 更新 {relabeled} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
