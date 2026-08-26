import os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings().all()]
print("distinct source in business_fields:")
for r in q("SELECT DISTINCT source, count(*) n FROM rules.business_fields GROUP BY source ORDER BY source"):
    print(r)
print("\ndistinct source_key in dynamic_source_fields:")
for r in q("SELECT DISTINCT source_key, count(*) n FROM rules.dynamic_source_fields GROUP BY source_key ORDER BY source_key"):
    print(r)
