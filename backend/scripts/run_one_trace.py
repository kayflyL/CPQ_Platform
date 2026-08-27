# -*- coding: utf-8 -*-
"""进程内单案例跟踪：实时打印节点开始/结束、LLM 调用耗时/输入输出字符数、抽槽与配件落地产物。"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_generalization import CASES
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.skill_plan_executor import run_skill_plan
from app.services import llm_client

_G_T0 = None
_orig_chat_json = llm_client.chat_json


def _input_chars(messages) -> int:
    n = 0
    for m in (messages or []):
        if isinstance(m, dict):
            n += len(str(m.get("content") or ""))
    return n


async def _chat_json_trace(messages, schema=None, model=None, temperature=None,
                           timeout=90.0, max_attempts=2, max_tokens=None,
                           thinking=None, reasoning_effort=None):
    in_chars = _input_chars(messages)
    now = (time.perf_counter() - _G_T0) if _G_T0 is not None else 0.0
    print(f"[{now:6.1f}s]   LLM_START model={model or 'default'} in_chars={in_chars} msgs={len(messages or [])}", flush=True)
    t1 = time.perf_counter()
    try:
        data = await _orig_chat_json(messages, schema=schema, model=model, temperature=temperature,
                                     timeout=timeout, max_attempts=max_attempts, max_tokens=max_tokens,
                                     thinking=thinking, reasoning_effort=reasoning_effort)
    except Exception as e:
        now2 = (time.perf_counter() - _G_T0) if _G_T0 is not None else 0.0
        print(f"[{now2:6.1f}s]   LLM_FAIL took={time.perf_counter()-t1:.1f}s err={type(e).__name__}: {str(e)[:140]}", flush=True)
        raise
    out_chars = len(json.dumps(data, ensure_ascii=False))
    now2 = (time.perf_counter() - _G_T0) if _G_T0 is not None else 0.0
    print(f"[{now2:6.1f}s]   LLM_DONE took={time.perf_counter()-t1:.1f}s out_chars={out_chars}", flush=True)
    return data


llm_client.chat_json = _chat_json_trace


async def main(label):
    global _G_T0
    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis")
    finally:
        repo.close()
    text = dict(CASES).get(label)
    if not text:
        print("unknown label", label)
        return
    t0 = time.perf_counter()
    _G_T0 = t0

    async def broadcast(payload):
        t = payload.get("type")
        now = time.perf_counter() - t0
        if t == "step_start":
            print(f"[{now:6.1f}s] START {payload.get('step')}", flush=True)
        elif t == "step_done":
            print(f"[{now:6.1f}s] DONE  {payload.get('step')} {payload.get('duration_ms')}ms", flush=True)
        elif t == "step_progress":
            sub = payload.get("sub") or {}
            kind = sub.get("kind") or ""
            tool = sub.get("tool") or ""
            text_snip = str(sub.get("text") or "")[:80]
            print(f"[{now:6.1f}s]   {kind} {tool} {text_snip}", flush=True)
        elif t == "need_input":
            print(f"[{now:6.1f}s] NEED_INPUT {payload.get('question')}", flush=True)

    initial_ctx = {
        "force_complete": True,
        "output_kind": "bom_scheme_draft",
        "business_mode": "conversation",
        "operator_name": "trace",
        "history": [],
    }
    ctx = await run_skill_plan("trace", text, flow, broadcast, initial_ctx=initial_ctx)
    total = round(time.perf_counter() - t0, 1)
    print(f"TOTAL {total}s timings={ctx.get('timings')}", flush=True)
    ext = ctx.get("ext") or {}
    print("MODEL", ext.get("server_type_name"), ext.get("form"), ext.get("series"), flush=True)
    print("FILL_MISSING", ctx.get("agent_fill_missing"), flush=True)
    print("MODEL_SELECTION", json.dumps(ctx.get("model_selection") or {}, ensure_ascii=False), flush=True)
    for k in ("server_type_name", "series", "form", "purchase_qty", "categories",
              "cpu_signal", "mem_signal", "drive_groups", "gpu_groups",
              "raid_groups", "psu_signal", "multi_spec_filters"):
        v = ext.get(k)
        if v not in (None, "", []):
            print(f"EXT.{k} = {json.dumps(v, ensure_ascii=False)}", flush=True)
    print("PLANS", [p.get("name") for p in (ctx.get("plans") or [])], flush=True)
    for mid, parts in (ctx.get("kp_by_model") or {}).items():
        for p in parts:
            flag = "UNMATCH" if p.get("unmatched") else ("MISMATCH" if p.get("spec_mismatch") else "ok")
            print(f"  [{flag}] {p.get('category')} | {p.get('pn')} | req={p.get('request_spec') or ''} got={p.get('grounded_spec') or ''}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "C1-A800x2"))
