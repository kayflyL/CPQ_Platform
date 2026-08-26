import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
with engine.connect() as c:
    v = c.execute(text("SELECT value FROM rules.system_config WHERE key='reasoning_node_defaults'")).scalar()
d = json.loads(v) if isinstance(v,str) else v
ra = d["requirement_analysis"]
for node, cfg in ra.items():
    print("="*90)
    print("NODE:", node)
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
