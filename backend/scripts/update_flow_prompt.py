import json, sys, os
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
ROOT = r"D:\CPQ_Platform_V1"
JSON_PATH = os.path.join(ROOT, "backend", "app", "services", "reasoning_prompt_defaults.json")
with open(JSON_PATH, encoding="utf-8") as f:
    seed = json.load(f)
NEW = seed["agent_fill"]["system_prompt"]
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
repo = ReasoningFlowRepository()
try:
    flow = repo.get_active_flow()
    if not flow:
        print("NO active flow"); sys.exit(0)
    fid = flow.get("id")
    nc = flow.get("node_configs") or {}
    cfg = dict(nc.get("agent_fill") or {})
    prompt = dict(cfg.get("prompt") or {})
    old_len = len(str(prompt.get("system_prompt") or ""))
    prompt["system_prompt"] = NEW
    cfg["prompt"] = prompt
    repo.upsert_node_config(fid, "agent_fill", cfg, operator="system")
    print("flow_id=", fid, "| old_len=", old_len, "-> new_len=", len(NEW))
finally:
    repo.close()
