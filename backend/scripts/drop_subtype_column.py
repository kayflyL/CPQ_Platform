"""DROP l6.parts_master.sub_type 列（sub_type 已迁到 specs，见 backfill_specs_from_subtype.py）。

默认 dry-run（查列是否存在 + 统计剩余非空行），--commit 才真 DROP。
DROP 前确认：运行时代码（backend/app、frontend/src）已全部清除 sub_type 读写。
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正 DROP（默认 dry-run）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor()

cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema='l6' AND table_name='parts_master' AND column_name='sub_type'"
)
exists = cur.fetchone()
if not exists:
    print("l6.parts_master.sub_type 列不存在，无需 DROP")
else:
    cur.execute("SELECT COUNT(*) FROM l6.parts_master WHERE sub_type IS NOT NULL AND sub_type <> ''")
    n = cur.fetchone()[0]
    cur.execute(
        "SELECT category, COUNT(*) FROM l6.parts_master "
        "WHERE sub_type IS NOT NULL AND sub_type <> '' GROUP BY category ORDER BY category"
    )
    breakdown = cur.fetchall()
    print(f"列存在；sub_type 非空行数: {n}")
    for cat, cnt in breakdown:
        print(f"  - {cat}: {cnt}")
    if args.commit:
        cur.execute("ALTER TABLE l6.parts_master DROP COLUMN sub_type")
        conn.commit()
        print("已 DROP COLUMN sub_type")
    else:
        print("DRY-RUN；确认加 --commit")

conn.close()
