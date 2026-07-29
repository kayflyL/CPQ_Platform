"""Requirement intelligence API — 商机详情页「生成报价」推理流。

POST /api/reasoning/{opportunity_id}/generate 触发后台 pipeline（jieba 分词 → 聚合检索），
立即返回 202；推理步骤通过 reasoning_hub 经 WS /api/reasoning/ws/{opportunity_id} 实时推送。

与聊天助手通道物理隔离：pipeline 一期纯本地，不调 LLM。
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services.reasoning_hub import reasoning_hub
from app.services.requirement_intel_service import run_pipeline

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])


class GenerateBody(BaseModel):
    requirement_text: str = ""
    supplement_text: Optional[str] = None       # 反答回填文本
    explicit_budget: Optional[float] = None     # 用户明确给预算
    force_complete: bool = False                # 跳过反问，强制走选型


# 正在跑的 pipeline 句柄（防止同一商机并发重入；弱保护，进程内有效）
_running: dict[str, asyncio.Task] = {}


@router.post("/{opportunity_id}/generate", status_code=202)
async def generate(opportunity_id: str, body: GenerateBody):
    """触发一条推理 pipeline。幂等：同一商机正在跑则先取消旧的（含短暂等待避免事件交错）。"""
    text = (body.requirement_text or "").strip()
    supplement_text = (body.supplement_text or "").strip()
    if not text and not supplement_text:
        return {"status": "ignored", "reason": "empty"}

    supplement = None
    if supplement_text or body.explicit_budget is not None:
        supplement = {"text": supplement_text or None, "budget": body.explicit_budget}

    # 并发保护：取消旧 task + 短暂等待（前端也按 pipeline_id 过滤过期消息双保险）
    prev = _running.get(opportunity_id)
    if prev and not prev.done():
        prev.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(prev), timeout=0.3)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass

    task = asyncio.create_task(run_pipeline(
        opportunity_id, text,
        supplement=supplement,
        force_complete=body.force_complete,
    ))
    _running[opportunity_id] = task
    # 完成后清理
    def _cleanup(_t):
        _running.pop(opportunity_id, None)
    task.add_done_callback(_cleanup)

    return {"status": "started", "opportunity_id": opportunity_id}


@router.websocket("/ws/{opportunity_id}")
async def reasoning_ws(ws: WebSocket, opportunity_id: str):
    """订阅该商机的推理步骤流（step_start/step_done/candidates_ready/pipeline_done/error）。"""
    await reasoning_hub.connect(ws, opportunity_id)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await reasoning_hub.disconnect(ws)
