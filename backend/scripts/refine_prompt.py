# -*- coding: utf-8 -*-
import json, io, os, sys
ROOT = r"D:\CPQ_Platform_V1"
JSON_PATH = os.path.join(ROOT, "backend", "app", "services", "reasoning_prompt_defaults.json")
with io.open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)
p = data["agent_fill"]["system_prompt"]

old3 = "3) 只有「下游选型真的需要 + 客户没说 + 客户也没委托」的字段才反问，一次只反问最关键的一个，用一句话。"
new3 = (
    "3) 只有「下游选型真的需要 + 客户没说 + 客户也没委托」的字段才反问，一次只反问最关键的一个，用一句话。\n"
    "   客户已给出「服务器类型 + 机箱形态 + 主要硬件（CPU/内存/磁盘/网卡/电源等）」时，已足以进入下游选型："
    "此时系列/平台（series/platform_type）不是必答项，直接不在 fill 里写它，done 置 true，把系列交给下游按候选给出；"
    "绝不要因为没给系列就反问“系列/平台偏好”。只有服务器类型、机箱形态、关键硬件三项都明显不足时才 done=false 反问。"
)
assert old3 in p, "old3 not found"
p = p.replace(old3, new3)

old_lead = ("先参考【在售目录参考】，把 server_type / series / form 映射到真实在售值；能从需求上下文（“机架式 / 2U”等）合理推断就推断；"
            "若多个在售类型都可能且影响选型，才反问一次。")
new_lead = ("先参考【在售目录参考】，把 server_type / series / form 映射到真实在售值；能从需求上下文（“机架式 / 2U”等）合理推断就推断；"
            "系列/平台普通场景下交给下游按候选给出，不必替客户选定。")
if old_lead in p:
    p = p.replace(old_lead, new_lead)

data["agent_fill"]["system_prompt"] = p
with io.open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.repository.system_config_repo import SystemConfigRepository
repo = SystemConfigRepository()
try:
    v = repo.get_value("reasoning_prompts", None) or {}
    if isinstance(v, dict):
        v.setdefault("agent_fill", {})["system_prompt"] = p
        repo.set("reasoning_prompts", v, type="json", description="需求分析节点提示词/话术默认值（用户可在节点抽屉覆盖）", operator="system")
        print("DB system_config updated len=", len(p))
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
        print("flow node config updated flow_id=", fid)
finally:
    r2.close()
print("done")
