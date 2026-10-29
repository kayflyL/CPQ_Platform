# -*- coding: utf-8 -*-
"""全库自增序列体检/校准:合并迁库后序列常落后于 max(id),INSERT 撞唯一键。
默认只盘点(--check);--fix 执行 setval 校准。幂等,可重复跑。"""
import sys

from sqlalchemy import text

from app.models.base import engine

SCHEMAS = ("kp", "l6", "l6_history", "opportunities", "rules", "parts", "public", "ai_read")

# 带整型默认值自增的列(serial/identity)与其序列
FIND_SQL = text("""
SELECT n.nspname AS schema, c.relname AS table_name, a.attname AS col,
       pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) AS seq,
       (SELECT pg_sequences.last_value FROM pg_sequences
         WHERE pg_sequences.schemaname = n.nspname AND pg_sequences.sequencename
               = split_part(pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname), '.', 2))
       AS seq_last
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(:schemas) AND c.relkind = 'r'
  AND a.attnum > 0 AND NOT a.attisdropped
  AND pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) IS NOT NULL
  AND EXISTS (SELECT 1 FROM pg_constraint pk
              WHERE pk.conrelid = c.oid AND pk.contype = 'p' AND a.attnum = ANY(pk.conkey))
""")


def main() -> None:
    fix = "--fix" in sys.argv
    with engine.connect() as s:
        rows = s.execute(FIND_SQL, {"schemas": list(SCHEMAS)}).fetchall()
        behind = []
        for schema, table, col, seq, seq_last in rows:
            if not seq:
                continue
            try:
                mx = s.execute(text(
                    f'SELECT COALESCE(max("{col}"), 0) FROM "{schema}"."{table}"')).scalar()
            except Exception:
                continue  # 无整型 max 的非常规表跳过
            effective = seq_last or 0
            if mx and effective < mx:
                behind.append((schema, table, col, effective, mx))
                if fix:
                    s.execute(text(
                        "SELECT setval(:seq, :mx, true)"), {"seq": seq, "mx": mx})
            elif not mx and effective and fix:
                pass  # 空表不回拨,避免并发回绕
        print(f"扫描 {len(rows)} 张带自增主键的表,序列滞后 {len(behind)} 张:")
        for schema, table, col, seq_last, mx in behind:
            print(f"  {schema}.{table}.{col}: seq={seq_last} < max={mx}" + ("  -> 已校准" if fix else ""))
        if fix:
            s.commit()
            print("校准完成")


if __name__ == "__main__":
    main()
