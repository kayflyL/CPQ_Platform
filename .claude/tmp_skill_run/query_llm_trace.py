# -*- coding: utf-8 -*-
"""查 llm_trace 逐调用记录（放 tmp 目录，避免触发 uvicorn --reload）。
用法：backend/.venv/Scripts/python.exe -X utf8 .claude/tmp_skill_run/query_llm_trace.py <thread_id>"""
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
tid = sys.argv[1]
from app.models.base import Rules_SessionLocal
from app.models.llm_trace import LLMTrace
s = Rules_SessionLocal()
rows = (s.query(LLMTrace)
        .filter(LLMTrace.opportunity_id == tid)
        .order_by(LLMTrace.id).all())
print(f"共 {len(rows)} 条 LLM 调用")
prev = None
total = 0.0
for r in rows:
    gap = ""
    if prev is not None:
        gap = f" (+{(r.created_at - prev).total_seconds():.1f}s)"
    prev = r.created_at
    total += r.duration_ms or 0
    print(f"  #{r.id} {r.node_type:28s} {r.status:8s} {r.duration_ms or 0:>7}ms "
          f"prompt={r.prompt_chars or 0:>6} resp={r.response_chars or 0:>6} {r.created_at}{gap}"
          + (f" err={r.error[:80]}" if r.error else ""))
print(f"LLM 纯生成累计 {total/1000:.1f}s")
