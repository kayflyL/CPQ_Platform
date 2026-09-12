# -*- coding: utf-8 -*-
"""LLM 延迟探针（2026-09-12 D+B）：回答三个问题，数据落 rules.llm_trace agent_round 之外单跑。

1. 前缀缓存：同一段大前缀连打两次，第二次 prompt_cache_hit_tokens 是否 >0（DeepSeek 自动缓存是否穿透 relay）。
2. effort 透传：reasoning_effort=None vs low，思考量/时长差多少（S5「代理忽略 effort」假设的直接验证）。
3. usage 捕获：stream_options=include_usage 是否被 relay 接受（不接受则 usage 恒空）。

用法：.venv/Scripts/python.exe -X utf8 scripts/llm_latency_probe.py
"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import llm_client

# 模拟 skill 真实体量的 system（左栏规则 2555 + steps 1219 + 节点使命 1200 ≈ 5K 字）
PREFIX = ("你是 AI 同事「技术支持工程师」，正在执行「需求分析」任务。\n\n任务规则（配置者编写，全程遵守）：\n"
          + "1. 严格按客户原话登记，型号/数量/单位不改写不丢，容量必须带单位。2. 工具纪律=说到做到。"
          "3. 检索时中文用途词先换成库内数值/型号词。4. 一次只问一件事。5. 推荐必须带理由。\n" * 40
          + "\nsteps 清单：[input, agent_fill, model_reason, kp_reason, compose, output]\n")
TASK = "客户要一台 2U 通用服务器，兆芯 50000 双路，768GB DDR5，4 块 6T HDD。请用一句话复述你理解的关键配置。"


async def one_call(label: str, *, effort=None, prefix: str = PREFIX) -> dict:
    messages = [
        {"role": "system", "content": prefix},
        {"role": "user", "content": TASK},
    ]
    t0 = time.perf_counter()
    reasoning_chars = 0
    content_chars = 0
    usage = {}
    try:
        stream = llm_client.stream_agent_chat(
            messages, temperature=0.0, reasoning_effort=effort,
            first_token_timeout=60.0, overall_timeout=300.0)
        async for item in stream:
            t = item.get("type")
            if t == "reasoning":
                reasoning_chars += len(item.get("delta") or "")
            elif t == "content":
                content_chars += len(item.get("delta") or "")
            elif t == "usage":
                usage = item.get("usage") or {}
    except Exception as e:
        print(f"[{label}] 失败: {e}")
        return {}
    dur = time.perf_counter() - t0
    print(f"[{label}] {dur:6.1f}s 思考{reasoning_chars:>6}字 正文{content_chars:>4}字 "
          f"usage={usage or '(未返回)'}")
    return {"dur": dur, "think": reasoning_chars, "usage": usage}


async def main() -> None:
    print(f"== 前缀体量：{len(PREFIX)} 字")
    print("== 1) 前缀缓存（同一前缀连打两次，看 cache_hit_tokens）")
    a = await one_call("cache-cold")
    await asyncio.sleep(2)
    b = await one_call("cache-warm")
    print("== 2) effort 透传（None vs low，同一任务）")
    c = await one_call("effort-default")
    d = await one_call("effort-low", effort="low")
    print("\n== 结论素材")
    if a.get("usage") or c.get("usage"):
        print("  usage 捕获：OK（relay 接受 include_usage）")
        hit = (b.get("usage") or {}).get("cache_hit_tokens")
        print(f"  前缀缓存：cold={ (a.get('usage') or {}).get('cache_hit_tokens') } "
              f"warm={hit} → {'命中，缓存穿透 relay 生效' if (hit or 0) > 0 else '未命中（relay/模型不吃前缀缓存）'}")
    else:
        print("  usage 捕获：失败（relay 不吐 usage 或不接受 stream_options）")
    if c and d:
        speed = (c['dur'] / d['dur']) if d['dur'] else 0
        shrink = (c['think'] / d['think']) if d['think'] else 0
        print(f"  effort=low：时长 {c['dur']:.1f}s → {d['dur']:.1f}s"
              f"（{speed:.1f}x），思考 {c['think']} → {d['think']} 字（{shrink:.1f}x）")


if __name__ == "__main__":
    asyncio.run(main())
