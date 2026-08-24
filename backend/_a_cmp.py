# -*- coding: utf-8 -*-
"""对比 chat_json vs stream_agent_chat 正文内容（临时，验证后删）。"""
import asyncio, sys
sys.path.insert(0, ".")
from app.services import llm_client

MSGS = [
    {"role": "system", "content": "你是需求分析助手。信息不足请反问。每轮只输出一个 JSON 对象。"},
    {"role": "user", "content": "需求：我需要一台 AMD 服务器，用于 AI 推理，2U。\n\n参考：当前缺类型/系列/CPU/内存/存储/GPU/网卡/电源/预算。"},
]

async def main():
    # chat_json
    try:
        d = await llm_client.chat_json(MSGS, max_attempts=1)
        print("CHAT_JSON=", d)
    except Exception as e:
        print("CHAT_JSON_ERR=", type(e).__name__, str(e)[:120])
    # stream_agent_chat
    text = ""
    think = ""
    async for item in llm_client.stream_agent_chat(llm_client._ensure_json_instruction(MSGS)):
        if item.get("type") == "content":
            text += item.get("delta") or ""
        else:
            think += item.get("delta") or ""
    print("STREAM_THINK_LEN=", len(think))
    print("STREAM_CONTENT=", text[:400])
    try:
        p = llm_client._parse_json_content(text)
        print("STREAM_PARSED=", p)
    except Exception as e:
        print("STREAM_PARSE_ERR=", e)

asyncio.run(main())
