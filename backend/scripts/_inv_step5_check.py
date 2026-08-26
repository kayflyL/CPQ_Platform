import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text

with engine.connect() as c:
    v = c.execute(text("SELECT value FROM rules.system_config WHERE key='kp_slot_group_map'")).scalar()
cfg = json.loads(v) if isinstance(v, str) else v
changed = False
for k, item in (cfg or {}).items():
    if isinstance(item, dict) and "label" in item:
        item.pop("label", None); changed = True
if changed:
    with engine.begin() as c:
        c.execute(text("UPDATE rules.system_config SET value=:v WHERE key='kp_slot_group_map'"), {"v": json.dumps(cfg, ensure_ascii=False)})
    print("DB kp_slot_group_map: stripped label")
else:
    print("DB kp_slot_group_map: already no label")

# verify combined_slot_spec part labels
from app.services.requirement_slots import combined_slot_spec
for s in combined_slot_spec():
    if s.get("src_type") == "kp":
        print("KP slot:", s["key"], "->", s["label"])
