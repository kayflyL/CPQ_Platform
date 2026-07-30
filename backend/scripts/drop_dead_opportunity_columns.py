"""清理:DROP opportunities.opportunities 的死字段列。

本批移除三个"功能废弃但字段残留"的死列（无输入口致恒空 / 零有效消费方）：
  - win_reason     中标原因 — D1 复盘功能创建，从未接通（lost_reason 的镜像，零消费）
  - lost_reason    丢标原因 — 仅 AI 趋势报告引用，但无输入口致恒空；连带消费代码一并移除
  - quote_scenario 报价场景 — 喂计价分档/策略画布，但无输入口致恒空，计价场景维度实为空转；连带移除

前置：代码已完全不读不写这三列（model/repo/seed/type/消费方均已清理）。
不可逆。幂等（列不存在则跳过）。用法：
  python -X utf8 scripts/drop_dead_opportunity_columns.py            # dry-run
  python -X utf8 scripts/drop_dead_opportunity_columns.py --apply    # 执行

回滚（如需）：
  ALTER TABLE opportunities.opportunities
    ADD COLUMN IF NOT EXISTS win_reason TEXT,
    ADD COLUMN IF NOT EXISTS lost_reason TEXT,
    ADD COLUMN IF NOT EXISTS quote_scenario VARCHAR;
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings


TABLE = "opportunities.opportunities"
COLS = ["win_reason", "lost_reason", "quote_scenario"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行(默认 dry-run)")
    args = ap.parse_args()

    s = get_settings()
    conn = psycopg2.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
    )
    print(f"=== drop_dead_opportunity_columns {'APPLY' if args.apply else 'DRY-RUN'} ===")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='opportunities' AND table_name='opportunities'
              AND column_name = ANY(%s)
        """, (COLS,))
        to_drop = [r[0] for r in cur.fetchall()]
        if not to_drop:
            print("  dead columns already gone — nothing to do")
        else:
            for col in to_drop:
                print(f"  DROP COLUMN {TABLE}.{col}")
            if args.apply:
                cols_sql = ", ".join(f"DROP COLUMN IF EXISTS {c}" for c in to_drop)
                cur.execute(f"ALTER TABLE {TABLE} {cols_sql}")
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
