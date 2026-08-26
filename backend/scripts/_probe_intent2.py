import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.workflow_intent import resolve_intent
CTX = "当前所在环节：model_reason\nAI 上一条问的是：我需要一台服务器\n客户已表达需求：我需要一台服务器\n当前候选机型：ES22V3-P、ZS22V2-P"
async def run():
    for msg in ["这个多少钱", "这台什么配置", "这两种有什么区别", "有GPU的吗", "通用计算", "我要一台AI训练服务器"]:
        r = await resolve_intent(msg, CTX)
        print(msg, "->", json.dumps(r, ensure_ascii=False))
asyncio.run(run())
