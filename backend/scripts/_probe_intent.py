import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.workflow_intent import resolve_intent

CTX = "当前所在环节：model_reason\nAI 上一条问的是：我需要一台服务器\n客户已表达需求：我需要一台服务器"

async def run():
    for msg in ["都有哪些服务器", "啥意思", "我要一台通用计算服务器，2U", "取消", "这个多少钱", "你推荐吧", "选第一个"]:
        r = await resolve_intent(msg, CTX)
        print(msg, "->", json.dumps(r, ensure_ascii=False))

asyncio.run(run())
