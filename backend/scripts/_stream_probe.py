# -*- coding: utf-8 -*-
import asyncio, os, sys, time
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)
async def main():
    from app.services import llm_client
    msgs = [{"role":"system","content":"只输出一个 JSON 对象：{\"action\":\"final\",\"answer\":{\"requirement\":{\"form\":\"4U\"}}}"},{"role":"user","content":"AI训练 4U 8卡"}]
    t0=time.time()
    try:
        async for item in llm_client.stream_agent_chat(llm_client._ensure_json_instruction(msgs)):
            pass
        print("stream ok %.1fs" % (time.time()-t0))
    except Exception as e:
        print("stream fail %.1fs %s" % (time.time()-t0, repr(e)[:200]))
asyncio.run(main())
