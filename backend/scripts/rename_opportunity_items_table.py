"""重命名表：opportunities.opportunity_items → opportunities.quotation_items

一次性迁移：修正历史遗留命名，使表名与业务语义一致。
"""
import sqlalchemy
from sqlalchemy import text

engine = sqlalchemy.create_engine(
    "postgresql://postgres:961216@localhost:5432/cpq_platform?client_encoding=UTF8"
)

with engine.begin() as conn:
    # 检查表是否存在
    result = conn.execute(text(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='opportunities' AND table_name='opportunity_items')"
    ))
    if not result.scalar():
        print("✗ 表 opportunities.opportunity_items 不存在，可能已迁移")
        exit(1)

    # 重命名表
    conn.execute(text("ALTER TABLE opportunities.opportunity_items RENAME TO quotation_items"))
    print("✓ 表已重命名：opportunities.opportunity_items → opportunities.quotation_items")

    # 验证
    result = conn.execute(text(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='opportunities' AND table_name='quotation_items')"
    ))
    if result.scalar():
        print("✓ 验证通过：新表名 quotation_items 已存在")
    else:
        print("✗ 验证失败：新表名不存在")
        exit(1)