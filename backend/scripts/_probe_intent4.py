import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.workflow_intent import resolve_intent
CTX="当前所在环节：model_reason\nAI 上一条问的是：需要一台服务器\n客户已表达需求：我需要一台服务器"
async def run():
    for msg in ["我就想和你聊天，不想要服务器", "算了，不配了", "谢谢哈哈", "取消配置"]:
        print(msg, "->", json.dumps(await resolve_intent(msg, CTX), ensure_ascii=False))
asyncio.run(run())
