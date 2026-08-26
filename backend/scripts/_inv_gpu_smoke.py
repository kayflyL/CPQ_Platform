import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.services.capabilities import run_select_baseline_rule

def run(ext, scene=None):
    ctx = {"ext": ext, "scene": scene or {}, "delegated": False, "requirement_text": "3张GPU"}
    cfg = {"rule_types": ["fallback_order", "gpu_form_map", "compliance_map"]}
    out = run_select_baseline_rule(ctx, cfg)
    print("--- ext:", json.dumps(ext, ensure_ascii=False))
    for b in ctx["baselines"]:
        print("  ", b.get("name"), "| form=", b.get("form"), "| series=", b.get("series"), "| gpu_slots=", (b.get("base_config") or {}).get("gpu_slots"), "| note=", b.get("gpu_capacity_note"))
    print("  count=", out.get("count"))

print("== 3 GPU, Orion AI ==")
run({"server_type_name": "AI / 加速计算服务器", "series": "Orion", "gpu_groups": [{"qty": 3}]})
print("\n== 3 GPU, no series/form, AI ==")
run({"server_type_name": "AI / 加速计算服务器", "gpu_groups": [{"qty": 3}]})
print("\n== 12 GPU, Orion AI (none capable) ==")
run({"server_type_name": "AI / 加速计算服务器", "series": "Orion", "gpu_groups": [{"qty": 12}]})
