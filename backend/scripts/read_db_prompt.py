import json, sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.repository.system_config_repo import SystemConfigRepository
repo = SystemConfigRepository()
try:
    v = repo.get_value("reasoning_prompts", None)
    if v:
        af = (v or {}).get("agent_fill") or {}
        sp = af.get("system_prompt") or ""
        print("has agent_fill system_prompt:", bool(sp))
        print("len:", len(sp))
        print("first120:", sp[:120])
        print("contains 需求层 only:", "需求层" in sp, "| 绝不替下游: ", "绝不替下游决定机型" in sp)
    else:
        print("NO reasoning_prompts key")
finally:
    repo.close()
