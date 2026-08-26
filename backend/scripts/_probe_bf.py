import os, json
os.environ.setdefault("PYTHONUTF8","1")
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from sqlalchemy import inspect, text
from app.models.base import Rules_SessionLocal, Opportunity_SessionLocal

rs = Rules_SessionLocal()
osess = Opportunity_SessionLocal()

print("=== rules.business_fields ===")
rows = rs.execute(text("SELECT id,key,category,source,source_column,enabled,export_visible,is_core_field,used_in_pages FROM rules.business_fields ORDER BY category,id")).mappings().all()
for r in rows:
    print(r["id"], "|", r["key"], "|", r["category"], "|", r["source"], "|", r["source_column"], "| en=",r["enabled"],"ev=",r["export_visible"],"core=",r["is_core_field"],"pages=",r["used_in_pages"])

print()
print("=== opportunities.opportunities columns ===")
insp = inspect(osess.get_bind())
cols = [c["name"] for c in insp.get_columns("opportunities", schema="opportunities")]
print(cols)

print()
print("=== rules.dynamic_source_fields ===")
dyn = rs.execute(text("SELECT id,source_key,field_key,enabled FROM rules.dynamic_source_fields ORDER BY source_key,id")).mappings().all()
for d in dyn:
    print(d["id"], "|", d["source_key"], "|", d["field_key"], "| en=", d["enabled"])

print()
print("=== rules.field_reference for the 6 keys ===")
keys = ("chassis_form","platform_type","purchase_qty","delivery_cycle","warranty_years","delivery_region")
refs = rs.execute(text("SELECT field_key,ref_type,ref_id,ref_name FROM rules.field_reference WHERE field_key IN :k"), {"k": keys}).mappings().all()
print(refs)

rs.close(); osess.close()
