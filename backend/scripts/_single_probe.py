# -*- coding: utf-8 -*-
import asyncio, os, sys, time
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)
async def main():
    from app.services.reasoning_executor import _run_single_shot
    config = {
        "system_prompt": "你是【需求分析 Agent】。把客户自然语言需求转成结构化槽位。只做理解与编排，不编价格/兼容/BOM。",
        "final_only_contract": "直接给出 JSON：{\"requirement\":{...},\"summary\":\"...\"}",
    }
    t0=time.time()
    res = await _run_single_shot("我要一台AI训练服务器，4U机箱，8块GPU，内存1TB，用于大模型训练", config, "[工具 load_requirement_rules 结果]\n{\"count\":14,\"rules\":{\"category_alias\":[{\"category\":\"GPU\",\"aliases\":[\"gpu\",\"显卡\"]}]}}")
    dt=time.time()-t0
    print("single_shot %.1fs ok=%s" % (dt, res.get("ok")))
    print("answer:", str(res.get("answer"))[:400])
asyncio.run(main())
