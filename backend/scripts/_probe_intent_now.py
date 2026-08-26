import asyncio, sys
sys.path.insert(0,".")
from app.services import workflow_intent as wi

async def main():
    ctx = "当前所在环节：需求分析\nAI 上一条问的是：请描述客户的工作负载和规格要求"
    for msg in ["你能介绍下ES22V3服务器吗", "你有哪些服务器", "我需要一台服务器", "介绍下ES22V3"]:
        d = await wi.resolve_intent(msg, ctx)
        print(repr(msg), "->", d.get("intent"), "reply=", (d.get("reply") or "")[:40])

asyncio.run(main())
