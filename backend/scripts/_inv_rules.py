import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]
def cols(s,t):
    return [(r["column_name"], r["data_type"]) for r in q(f"SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='{s}' AND table_name='{t}' ORDER BY ordinal_position")]

for s,t in [("rules","business_fields"),("rules","dynamic_source_fields"),("rules","kp_category_mapping"),("rules","parse_field_rules"),("rules","parse_regions"),("rules","field_references"),("rules","field_usage_stats")]:
    print(f"== {s}.{t} columns ==")
    for c,d in cols(s,t):
        print(" ", c, d)
    try:
        n = q(f"SELECT count(*) AS n FROM {s}.{t}")[0]["n"]
        print("   rows:", n)
    except Exception as e:
        print("   err", e)
