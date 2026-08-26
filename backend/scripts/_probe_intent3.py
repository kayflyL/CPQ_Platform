import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.workflow_intent import resolve_intent
CTX = "当前所在环节：model_reason\nAI 上一条问的是：需要一台服务器，请补充类型/系列/形态/预算\n客户已表达需求：我需要一台服务器"
async def run():
    for msg in ["玩游戏的有没有", "你是什么模型", "我就想和你聊天，不想要服务器", "谢谢", "这个多少钱", "通用计算"]:
        r = await resolve_intent(msg, CTX)
        print(msg, "->", json.dumps(r, ensure_ascii=False))
asyncio.run(run())
