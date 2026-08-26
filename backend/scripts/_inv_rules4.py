import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]

print("== requirement_rules count by type ==")
for r in q("SELECT type, count(*) n FROM rules.requirement_rules GROUP BY type ORDER BY type"):
    print(r)

print("\n== gpu_form_map rows ==")
for r in q("SELECT name, body FROM rules.requirement_rules WHERE type='gpu_form_map' ORDER BY id"):
    print(r["name"], json.dumps(r["body"], ensure_ascii=False))

print("\n== workload_map rows ==")
for r in q("SELECT name, body FROM rules.requirement_rules WHERE type='workload_map' ORDER BY id"):
    print(r["name"], json.dumps(r["body"], ensure_ascii=False))

print("\n== platform_series_map rows ==")
for r in q("SELECT name, body FROM rules.requirement_rules WHERE type='platform_series_map' ORDER BY id"):
    print(r["name"], json.dumps(r["body"], ensure_ascii=False))
