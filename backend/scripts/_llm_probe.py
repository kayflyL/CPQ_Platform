# -*- coding: utf-8 -*-
import asyncio, os, sys, time
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)
async def main():
    from app.services import llm_client
    print("llm_enabled:", llm_client.is_llm_enabled())
    t0 = time.time()
    try:
        data = await asyncio.wait_for(llm_client.chat_json([{"role":"user","content":"Reply with JSON: {\"ok\": true}"}]), timeout=60)
        print("chat_json ok in %.1fs" % (time.time()-t0))
        print("data:", str(data)[:300])
    except Exception as e:
        print("chat_json FAIL %.1fs: %s" % (time.time()-t0, repr(e)[:300]))
asyncio.run(main())
