import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]

print("== kp.kp_categories columns ==")
for r in q("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='kp' AND table_name='kp_categories' ORDER BY ordinal_position"):
    print(r["column_name"], r["data_type"])

print("\n== kp.kp_parts columns ==")
for r in q("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='kp' AND table_name='kp_parts' ORDER BY ordinal_position"):
    print(r["column_name"], r["data_type"])

print("\n== kp.kp_part_specs columns ==")
for r in q("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='kp' AND table_name='kp_part_specs' ORDER BY ordinal_position"):
    print(r["column_name"], r["data_type"])

print("\n== opportunities.opportunity_requirements columns ==")
for r in q("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='opportunities' AND table_name='opportunity_requirements' ORDER BY ordinal_position"):
    print(r["column_name"], r["data_type"])

print("\n== opportunities.opportunity_flow_nodes columns ==")
for r in q("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='opportunities' AND table_name='opportunity_flow_nodes' ORDER BY ordinal_position"):
    print(r["column_name"], r["data_type"])
