import json, os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.services.capabilities import run_select_baseline_rule, _enrich_agent_semantic, _gpu_qty_from_ext
from app.services.feasibility_guard import check_feasibility

# model selection smoke
def run(ext):
    ctx = {"ext": ext, "scene": {}, "delegated": False, "requirement_text": "3张GPU"}
    cfg = {"max_plans": None, "rule_types": ["fallback_order","compliance_map"], "recommend_strategy_id": None}
    run_select_baseline_rule(ctx, cfg)
    print("ext:", json.dumps(ext, ensure_ascii=False))
    for b in ctx["baselines"]:
        print("  ", b.get("name"), "form=", b.get("form"), "gpu_slots=", (b.get("base_config") or {}).get("gpu_slots"), "note=", b.get("gpu_capacity_note"))

print("== 3 GPU Orion AI ==")
run({"server_type_name": "AI / 加速计算服务器", "series": "Orion", "gpu_groups": [{"qty": 3}]})

# _enrich_agent_semantic: semantic.workload.gpu_count must NOT persist, gpu_groups must be written
print("\n== _enrich_agent_semantic (workload gpu_count -> gpu_groups, no dual write) ==")
ext = {"semantic": {"workload": {"kind": "llm_inference", "gpu_count": 8}}}
_enrich_agent_semantic(ext, {"rule_types": ["workload_map"]}, "需要训练大模型")
print("ext:", json.dumps(ext, ensure_ascii=False))

# feasibility guard
print("\n== feasibility_guard (3 GPU in 2U vs gpu_groups) ==")
print(check_feasibility({"form":"2U","server_type_name":"AI / 加速计算服务器","series":"Orion","gpu_groups":[{"qty":3}]}))
