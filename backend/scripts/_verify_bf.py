import os
os.environ.setdefault("PYTHONUTF8","1")
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
with engine.connect() as c:
    dead = c.execute(text("SELECT key FROM rules.business_fields WHERE key IN ('win_reason','lost_reason','quote_scenario')")).fetchall()
    print("dead rows remaining:", dead)
    rows = c.execute(text("SELECT key,source_column FROM rules.business_fields WHERE category='opportunity' AND source_column NOT IN ('slots','extra_fields') AND source_column IS NOT NULL ORDER BY key")).mappings().all()
    print("opportunity rows with non-null, non-slots/extra_fields source_column:")
    for r in rows: print(" ", r["key"], "->", r["source_column"])
