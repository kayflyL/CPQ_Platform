import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]

print("== kp.kp_categories rows ==")
for r in q("SELECT id,name,parent_id,sort_order,description FROM kp.kp_categories ORDER BY parent_id NULLS FIRST, id"):
    print(r)

print("\n== kp.kp_parts per category ==")
for r in q("""SELECT c.id,c.name,count(p.id) AS n
  FROM kp.kp_categories c LEFT JOIN kp.kp_parts p ON p.category_id=c.id
  GROUP BY c.id,c.name ORDER BY c.id"""):
    print(r)

print("\n== kp_part_specs distinct spec_key ==")
for r in q("SELECT spec_key, count(*) AS n FROM kp.kp_part_specs GROUP BY spec_key ORDER BY spec_key"):
    print(r)
