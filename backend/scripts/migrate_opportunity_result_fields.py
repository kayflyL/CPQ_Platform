"""D1 迁移：给 opportunities.opportunities 加 3 列（行业/订单类型/结果）。

用 opp_engine 执行（复用项目已配好的连接，无需手动连库）。
幂等：ADD COLUMN IF NOT EXISTS + UPDATE WHERE IS NULL，重跑无副作用。
等价于 migrations/add_opportunity_result_fields.sql。

用法（backend 目录）：python -X utf8 scripts/migrate_opportunity_result_fields.py
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

from sqlalchemy import text
from app.models.base import opp_engine


STATEMENTS = [
    "ALTER TABLE opportunities.opportunities "
    "ADD COLUMN IF NOT EXISTS industry      VARCHAR",
    "ALTER TABLE opportunities.opportunities "
    "ADD COLUMN IF NOT EXISTS order_type VARCHAR",
    "ALTER TABLE opportunities.opportunities "
    "ADD COLUMN IF NOT EXISTS result        VARCHAR DEFAULT 'pending'",
    "UPDATE opportunities.opportunities SET result = 'pending' WHERE result IS NULL",
]


def main():
    with opp_engine.begin() as conn:
        for stmt in STATEMENTS:
            conn.execute(text(stmt))
    print("✓ opportunities.opportunities 已加 3 列：")
    print("  industry / order_type / result")
    print("  result 历史空值已回填为 pending")


if __name__ == '__main__':
    main()
