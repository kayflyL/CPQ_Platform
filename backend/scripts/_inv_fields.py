import json, os
os.environ.setdefault("PYTHONUTF8", "1")
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text

def q(sql):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings().all()]

out = {}
# tables per schema
rows = q("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('kp','l6','opportunities','rules','parts') ORDER BY table_schema, table_name")
out["tables"] = [f"{r['table_schema']}.{r['table_name']}" for r in rows]

# columns for key tables
for schema, t in [("l6","server_types"),("l6","server_models"),("l6","base_configs"),("opportunities","opportunities")]:
    cols = q(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='{schema}' AND table_name='{t}' ORDER BY ordinal_position")
    out[f"cols::{schema}.{t}"] = [(c["column_name"], c["data_type"]) for c in cols]

print(json.dumps(out, ensure_ascii=False, indent=2))
