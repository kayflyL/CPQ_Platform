import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]
print("== business_fields opportunity scope (all) ==")
for r in q("SELECT key,label,source,source_column,type,enabled,scope FROM rules.business_fields WHERE category='opportunity' ORDER BY sort_order, id"):
    print(f"{r['key']:22} | {r['label']:12} | src={r['source']}.{r['source_column']} | {r['type']} | scope={r['scope']}")
print("\n== business_fields count by category ==")
for r in q("SELECT category, count(*) n FROM rules.business_fields GROUP BY category ORDER BY category"):
    print(r)
print("\n== field_usage_stats ==")
for r in q("SELECT field_key, usage_count, last_used_at FROM rules.field_usage_stats ORDER BY usage_count DESC"):
    print(r)
