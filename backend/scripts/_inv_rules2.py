import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]

print("== rules.business_fields ==")
for r in q("SELECT key,label,category,source,source_column,type,enabled,is_core_field,scope FROM rules.business_fields ORDER BY category, sort_order, id"):
    print(f"{r['category']:20} | {r['key']:28} | {r['label']:16} | src={r['source']}.{r['source_column']} | {r['type']} | en={r['enabled']} core={r['is_core_field']} scope={r['scope']}")

print("\n== rules.dynamic_source_fields ==")
for r in q("SELECT source_key,field_key,field_label,enabled FROM rules.dynamic_source_fields ORDER BY source_key, sort_order"):
    print(r)

print("\n== rules.kp_category_mapping ==")
for r in q("SELECT keyword,category,priority FROM rules.kp_category_mapping ORDER BY priority, id"):
    print(r)

print("\n== rules.parse_field_rules ==")
for r in q("SELECT field_key,region,source_type,source_config,fallback_config,enabled FROM rules.parse_field_rules ORDER BY id"):
    print(r)
