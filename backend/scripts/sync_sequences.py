"""一次性：同步所有表的 SERIAL 序列到 max(id)+1。

修复迁移后序列未同步问题——迁移脚本插带 id 数据后，SERIAL 序列仍停在 1，
新 INSERT 从 1 开始撞主键（l6_price_history 已踩过，其他表可能也有）。

幂等，可重复运行。用法：cd backend && python -X utf8 scripts/sync_sequences.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from sqlalchemy import create_engine, text

SCHEMAS = ['kp', 'l6', 'opportunities', 'rules', 'l6_history', 'public', 'parts']


def main():
    e = create_engine(get_settings().DATABASE_URL)

    with e.connect() as c:
        seqs = c.execute(text("""
            SELECT n.nspname AS schema, c.relname AS tbl, a.attname AS col,
                   pg_get_serial_sequence(n.nspname || '.' || c.relname, a.attname) AS seq
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE c.relkind = 'r'
              AND n.nspname = ANY(:schemas)
              AND a.attisdropped = false
              AND pg_get_serial_sequence(n.nspname || '.' || c.relname, a.attname) IS NOT NULL
            ORDER BY n.nspname, c.relname
        """), {"schemas": SCHEMAS}).mappings().all()

    print(f"Found {len(seqs)} serial sequences across schemas {SCHEMAS}.\n")
    for r in seqs:
        fq = f"{r['schema']}.{r['tbl']}"
        col = r['col']
        with e.begin() as c:
            mx = c.execute(text(f"SELECT max({col}) FROM {fq}")).scalar()
            new_val = (mx or 0) + 1
            c.execute(text("SELECT setval(:seq, :val, false)"), {"seq": r['seq'], "val": new_val})
        print(f"  {fq}.{col:<22} max={str(mx):<8} -> nextval={new_val}")
    print(f"\nDone. {len(seqs)} sequences synced.")


if __name__ == '__main__':
    main()
