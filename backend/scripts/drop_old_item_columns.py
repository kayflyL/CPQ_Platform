"""清理:DROP quotation_items 的旧列 part_name / spec(字段去重载完成后)。

前置:migrate_item_fields_rename.py 已把数据迁到 catalogue/description/part_category,
代码已完全不读不写 part_name/spec。本脚本删除这两列,释放空间、杜绝误用。

不可逆。幂等(列不存在则跳过)。用法:
  python -X utf8 scripts/drop_old_item_columns.py            # dry-run
  python -X utf8 scripts/drop_old_item_columns.py --apply    # 执行
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行(默认 dry-run)")
    args = ap.parse_args()

    s = get_settings()
    conn = psycopg2.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
    )
    print(f"=== drop_old_item_columns {'APPLY' if args.apply else 'DRY-RUN'} ===")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='opportunities' AND table_name='quotation_items'
              AND column_name IN ('part_name','spec')
        """)
        to_drop = [r[0] for r in cur.fetchall()]
        if not to_drop:
            print("  old columns already gone — nothing to do")
        else:
            for col in to_drop:
                print(f"  DROP COLUMN quotation_items.{col}")
            if args.apply:
                cols_sql = ", ".join(f"DROP COLUMN IF EXISTS {c}" for c in to_drop)
                cur.execute(f"ALTER TABLE opportunities.quotation_items {cols_sql}")
        if args.apply:
            conn.commit()
            print("\n✅ COMMITTED")
        else:
            conn.rollback()
            print("\n⚪ DRY-RUN (rolled back) — re-run with --apply to commit")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR (rolled back): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
