import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings().all()]

rows = q("SELECT key, type, description, length(value) AS vlen FROM rules.system_config ORDER BY key")
for r in rows:
    print(f"{r['key']}\t{r['type']}\tvlen={r['vlen']}\t{r['description']}")
