# -*- coding: utf-8 -*-
import asyncio, os, sys, time, json
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)

cases = [
    "我要一台AI训练服务器，4U机箱，8块GPU，内存1TB，用于大模型训练",
    "配置一台2U通用服务器，2颗CPU，128G内存，4块2.4T硬盘，用于虚拟化",
    "需要一台存储服务器，4U，12个3.5寸盘位，用于备份",
    "给我来台边缘计算小服务器，1U，低功耗，用于边缘推理",
]

async def main():
    from app.services.reasoning_executor import _handle_generic_agent
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository

    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
    finally:
        repo.close()
    cfg = (flow.get("node_configs") or {}).get("need_analysis") or {}

    async def noop(payload): pass

    for text in cases:
        ctx = {"requirement_text": text, "normalized_text": text, "history": [], "requirement": {}}
        t0 = time.time()
        res = await _handle_generic_agent(ctx, cfg, noop)
        dt = time.time()-t0
        struct = ctx.get("need_analysis")
        print("="*70)
        print("INPUT:", text)
        print("secs=%.1f ok=%s iterations=%s" % (dt, res.get("ok"), res.get("iterations")))
        print("STRUCT:", json.dumps(struct, ensure_ascii=False)[:800] if struct else "(none)")

asyncio.run(main())
