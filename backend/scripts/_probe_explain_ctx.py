import os, sys, asyncio
BE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BE))
from app.services.workflow_intent import resolve_intent

CTX = ("当前对话上下文：用户之前说要一台服务器，已暂停在“需求理解”节点追问类型。"
       "上一条助手回复列出了在售机型：通用计算服务器: ES22V3-P(Orion/2U), ZS22V2-P(Polaris/2U)；"
       "AI / 加速计算服务器: ESA24V3-P(Orion/4U) 等。用户现在问“你能介绍下ES22V3服务器吗”。"
       "需求原文：我想要一台服务器。")

async def main():
    for m in ["你能介绍下ES22V3服务器吗","介绍下ES22V3","这个型号怎么样"]:
        r = await resolve_intent(m, CTX)
        print(f"{m[:20]!r:22s} -> with_ctx intent={r.get('intent')} reply={(r.get('reply') or '')[:40]!r}")

asyncio.run(main())
