import sys, json
sys.path.insert(0, ".")
from app.services.capabilities import run_select_baseline_rule
ext={"server_type_name":"通用计算服务器","server_type":"通用计算服务器"}
ctx={"ext":ext,"requirement_text":"我需要一台服务器"}
res=run_select_baseline_rule(ctx,{})
baselines=ctx.get("baselines") or []
print("count=",res.get("count"),"matches=",len(res.get("matches") or []))
print("baselines=",[(b.get("name"),b.get("series"),b.get("form")) for b in baselines])
print("reason=",str(res.get("reason"))[:120])
