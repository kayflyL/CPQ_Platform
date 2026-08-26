import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]
with engine.connect() as c:
    v = c.execute(text("SELECT value FROM rules.system_config WHERE key='reasoning_node_defaults'")).scalar()
d = json.loads(v) if isinstance(v,str) else v
print("== reasoning_node_defaults top keys ==")
print(list(d.keys()) if isinstance(d, dict) else type(d))
if isinstance(d, dict):
    for k, val in d.items():
        if isinstance(val, dict):
            print(f"\n[{k}] keys: {list(val.keys())}")
        else:
            print(f"\n[{k}] = {val}")
