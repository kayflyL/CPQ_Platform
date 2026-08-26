import os
os.environ.setdefault("PYTHONUTF8","1")
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql,p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]
keys = ("chassis_form","platform_type","purchase_qty","delivery_cycle","warranty_years","delivery_region","win_reason","lost_reason","quote_scenario")
print("== field_references ==")
for r in q("SELECT field_key,ref_type,ref_id,ref_name FROM rules.field_references WHERE field_key IN :k", {"k": keys}):
    print(r)
print("== field_usage_stats ==")
for r in q("SELECT field_key,usage_count,last_used_at FROM rules.field_usage_stats WHERE field_key IN :k", {"k": keys}):
    print(r)
print("== parse_field_rules for keys ==")
for r in q("SELECT field_key,region,source_type,enabled FROM rules.parse_field_rules WHERE field_key IN :k", {"k": keys}):
    print(r)
print("== parse_field_rules ALL ==")
for r in q("SELECT field_key,region,enabled FROM rules.parse_field_rules ORDER BY field_key"):
    print(r)
