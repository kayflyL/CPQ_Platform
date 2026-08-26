import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql)).mappings().all()]

def cfg(key):
    r = q("SELECT value FROM rules.system_config WHERE key=:k", ) if False else None
    with engine.connect() as c:
        r = c.execute(text("SELECT value FROM rules.system_config WHERE key=:k"), {"k": key}).scalar()
    try:
        return json.loads(r) if isinstance(r, str) else r
    except Exception:
        return r

for key in ["requirement_slots", "kp_slot_group_map", "semantic_contract", "server_series", "server_form_factor", "kp_filter_dims"]:
    print("="*100)
    print("SYSTEM_CONFIG:", key)
    print(json.dumps(cfg(key), ensure_ascii=False, indent=2))
