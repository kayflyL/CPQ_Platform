# -*- coding: utf-8 -*-
"""临时诊断：跑 agent_fill，看配置/提示词/模型是否给出 fill JSON。"""
import asyncio
import json
import time
import sys

sys.path.insert(0, ".")

REQ = (
    "三、训推一体机\n"
    "【技术指标项40】1.品牌形态:非OEM，≥4U机架式服务器;\n"
    "【技术指标项41】2.处理器:配置≥2颗C86处理器三级缓存≥256MB，CPU主频≥2.6GHz，核数≥48;\n"
    "【技术指标项42】3.内存:配置≥2*64GB DDR5 RDIMM内存，最多支持24个内存插槽;"
    "硬盘:最多可支持≥12块3.5寸硬盘，其中最多可支持8块NVME SSD,实际配置≥2块480GB SATA SSD;\n"
    "【技术指标项43】4.风扇电源:实际配置≥4块2000W铂金电源，支持2+2冗余，"
    "配置≥12个热插拔风扇，支持N+1冗余;\n"
    "【技术指标项44】5.GPU:支持≥8块双宽PCIEGPU卡，GPU拓扑采用Balance拓扑结构设计，"
    "实际配置≥1张K100 64G GPU卡。"
)


async def main() -> None:
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services.capabilities import run_agent_fill

    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis")
    finally:
        repo.close()
    cfg = (flow.get("node_configs") or {}).get("agent_fill") or {}
    print("agent_fill config keys=", sorted(cfg.keys()))
    prompt = (cfg.get("prompt") if isinstance(cfg.get("prompt"), dict) else {})
    print("prompt.system_prompt len=", len(str(prompt.get("system_prompt") or "")))
    print("prompt.system_prompt head=", str(prompt.get("system_prompt") or "")[:120].replace("\n", " "))
    print("enabled_tools=", cfg.get("enabled_tools"))
    print("max_iterations=", cfg.get("max_iterations"))

    t0 = time.time()
    ctx = {"requirement_text": REQ, "ext": {}, "llm_enabled": True, "force_complete": False}
    try:
        res = await run_agent_fill(ctx, cfg)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("RUN FAILED")
        return
    dt = time.time() - t0
    print("elapsed_s=%.1f" % dt)
    print("result ok=", res.get("ok"))
    print("sufficient=", res.get("sufficient"))
    print("missing=", res.get("missing_critical"))
    print("question=", (res.get("question") or "")[:160])
    print("agent_answer=", str(res.get("agent_answer") or "")[:300])
    print("ext=", json.dumps(ctx.get("ext") or {}, ensure_ascii=False)[:600])
    print("tool_calls=", len(ctx.get("agent_fill_trace") or []))


if __name__ == "__main__":
    asyncio.run(main())
