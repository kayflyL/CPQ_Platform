# -*- coding: utf-8 -*-
import asyncio, os, sys, json
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)

queue = [
    {"requirement": {"server_type_name": "AI服务器", "server_type": "AI", "form": "4U", "gpu_count": 8, "gpu_groups": [{"kind": "GPU", "qty": 8}], "purchase_qty": 1, "usage": "大模型训练"}, "summary": "AI训练服务器 4U 8卡"},
    {"action": "recommend", "candidates": [{"config_id": 25, "name": "ESA24V3-P", "series": "", "form": "4U", "baseline": {"id": 25, "name": "ESA24V3-P", "form": "4U", "total_price": 23077.63, "max_dimm": 24}}], "recommended": {"name": "ESA24V3-P", "baseline": {"id": 25, "name": "ESA24V3-P", "form": "4U", "total_price": 23077.63}}, "reason": "4U 满足 8 卡", "baseline": {"id": 25, "name": "ESA24V3-P", "form": "4U", "total_price": 23077.63}},
    {"baseline": {"id": 25, "name": "ESA24V3-P", "form": "4U", "total_price": 23077.63}, "by_category": {"CPU": [], "Memory": []}, "parts": [{"category": "CPU", "name": "Xeon", "qty": 2, "unit_price": 5000.0}, {"category": "Memory", "name": "DDR5", "qty": 8, "unit_price": 200.0}], "summary": "8卡 1TB"},
    {"action": "build_bom", "baseline": {"id": 25, "name": "ESA24V3-P", "form": "4U", "total_price": 23077.63}, "parts": [{"category": "CPU", "name": "Xeon", "qty": 2, "unit_price": 5000.0}, {"category": "Memory", "name": "DDR5", "qty": 8, "unit_price": 200.0}], "cost": {"total_cost": 31305.63}, "summary": "方案要点"},
]

async def fake_chat(messages, model=None):
    return queue.pop(0)

async def main():
    from unittest.mock import patch
    import app.services.llm_client as llm
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services.capability_executor import run_fixed_workflow

    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
    finally:
        repo.close()

    events = []
    async def _collect(p):
        events.append(p)
    with patch.object(llm, "chat_json", fake_chat):
        ctx = await run_fixed_workflow("test-run", "我要AI训练服务器 4U 8卡 1TB", flow, _collect, initial_ctx={"force_complete": True})

    print("steps:", [p.get("step") for p in events if p.get("type")=="step_done"])
    print("plans:", len(ctx.get("plans") or []))
    print("requirement.form:", (ctx.get("requirement") or {}).get("form"))
    print("baseline:", (ctx.get("baseline") or {}).get("name"))
    print("parts_count:", len(ctx.get("parts") or []))
    print("flow_exit:", ctx.get("flow_exit"))

asyncio.run(main())
