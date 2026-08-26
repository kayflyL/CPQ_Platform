# -*- coding: utf-8 -*-
import asyncio, os, sys, json
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)

async def main():
    from app.services.agent_tools import _tool_select_models, _tool_select_parts, _tool_validate_compat, _tool_compute_price, _tool_load_requirement_rules
    req = await _tool_load_requirement_rules({"rule_types": ["category_alias", "gpu_form_map"]})
    print("rules:", req.get("count"))
    sm = await _tool_select_models({"server_type_name": "AI服务器", "form": "4U", "usage": "AI 训练"})
    print("select_models count:", sm.get("count"))
    cands = sm.get("candidates") or []
    if not cands:
        print("no candidates; try general")
        sm = await _tool_select_models({"server_type_name": "通用服务器", "form": "2U"})
        cands = sm.get("candidates") or []
        print("retry select_models count:", sm.get("count"))
    if not cands:
        return
    b = cands[0].get("baseline") or {}
    print("baseline:", {k: b.get(k) for k in ("id","name","form","total_price","max_dimm")})
    sp = await _tool_select_parts({"categories": ["CPU","Memory","HDD/SSD","NIC"], "server_type_name": str(b.get("name") or ""), "baseline": b})
    parts = sp.get("parts") or []
    print("select_parts count:", sp.get("count"), "first:", (parts[0] if parts else {}).get("category"))
    vc = await _tool_validate_compat({"baseline": b, "parts": parts, "requirement": {}})
    print("validate_compat ok:", vc.get("ok"), "violations:", len(vc.get("violations") or []), "warnings:", len(vc.get("warnings") or []))
    cp = await _tool_compute_price({"baseline": b, "parts": parts})
    print("compute_price:", cp.get("cost", {}).get("total_cost"), "kp_count:", cp.get("kp_count"))

asyncio.run(main())
