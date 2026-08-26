# -*- coding: utf-8 -*-
import json, io, os, sys
ROOT = r"D:\CPQ_Platform_V1"
JSON_PATH = os.path.join(ROOT, "backend", "app", "services", "reasoning_prompt_defaults.json")
old = "- 客户点名机型（写型号名，如 ES22V3-P / 联想 WA5480 G3）→ 把型号写进 fill.server_model；"
new = ("- 客户点名机型（写型号名，如 ES22V3-P / 联想 WA5480 G3）→ 先用 get_server_model / list_server_models 查在售目录，"
       "确认该型号是否存在并拿到其服务器类型、系列、机箱形态；查到就把型号写进 fill.server_model，并把查到的 type/series/form 一并登记；"
       "查不到就只填 server_model。done=true，不要因缺类型/系列/形态反问，机型是否在售由下游确认。")
data = json.load(io.open(JSON_PATH, "r", encoding="utf-8"))
p = data["agent_fill"]["system_prompt"]
assert old in p, "named-model bullet not found"
p = p.replace(old, new)
data["agent_fill"]["system_prompt"] = p
with io.open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")
print("JSON len=", len(p))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.repository.system_config_repo import SystemConfigRepository
repo = SystemConfigRepository()
try:
    v = repo.get_value("reasoning_prompts", None) or {}
    if isinstance(v, dict):
        v.setdefault("agent_fill", {})["system_prompt"] = p
        repo.set("reasoning_prompts", v, type="json", description="需求分析节点提示词/话术默认值（用户可在节点抽屉覆盖）", operator="system")
        print("DB system_config updated")
finally:
    repo.close()
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
r2 = ReasoningFlowRepository()
try:
    flow = r2.get_active_flow()
    if flow:
        fid = flow.get("id"); nc = flow.get("node_configs") or {}
        cfg = dict(nc.get("agent_fill") or {}); pr = dict(cfg.get("prompt") or {})
        pr["system_prompt"] = p; cfg["prompt"] = pr
        r2.upsert_node_config(fid, "agent_fill", cfg, operator="system")
        print("flow node config updated")
finally:
    r2.close()
print("done")
