import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.workflow_intent import reply_with_context, catalog_digest

async def main():
    cat = await catalog_digest()
    STATE = ("当前所在环节：model_reason\nAI 上一条问的是：需要一台服务器，请补充类型/系列/形态/预算\n"
             "客户已表达需求：我需要一台服务器")
    ctx = STATE + ("\n\n【在售目录】\n" + cat)
    for msg in ["都有哪些服务器", "啥意思", "玩游戏的有没有", "你是什么模型", "这个多少钱", "就选ES22V3-P吧"]:
        r = await reply_with_context(msg, ctx)
        print(msg, "->", r[:180])

asyncio.run(main())
