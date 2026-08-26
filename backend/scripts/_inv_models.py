import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text
def q(sql, p=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), p or {}).mappings().all()]

print("== l6.server_types ==")
for r in q("SELECT id,name,description,sort_order FROM l6.server_types ORDER BY sort_order"):
    print(r)

print("\n== l6.base_configs ==")
for r in q("SELECT id,name,server_type_id,series,model,form,bays,gpu_slots,max_cpu,max_dimm,mem_channels,psu_bays,max_tdp,gpu_arch_default,sort_order FROM l6.base_configs ORDER BY series,form,id"):
    print(r)

print("\n== l6.server_models ==")
for r in q("SELECT id,name,server_type_id,use,base_config_id,lifecycle_status,is_published FROM l6.server_models ORDER BY id"):
    print(r)
