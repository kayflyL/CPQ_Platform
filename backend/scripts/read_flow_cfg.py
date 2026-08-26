import json, sys, os
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
repo = ReasoningFlowRepository()
try:
    flow = repo.get_active_flow()
    if not flow:
        print("NO active flow")
    else:
        nc = flow.get("node_configs") or {}
        cfgn = nc.get("agent_fill") or {}
        print("node_configs keys:", list(nc.keys()))
        print("agent_fill keys:", list(cfgn.keys()))
        prompt = cfgn.get("prompt") or {}
        sp = prompt.get("system_prompt") or ""
        print("has prompt.system_prompt:", bool(sp), "| len:", len(sp))
        print("starts:", sp[:80])
        print("contains_new_marker '智能体':", "智能体" in sp)
        print("enabled_tools:", cfgn.get("enabled_tools"))
finally:
    repo.close()
