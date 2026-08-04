"""Requirement intelligence API — 商机详情页「生成报价」推理流。

POST /api/reasoning/{opportunity_id}/generate 触发后台 pipeline（jieba 分词 → 聚合检索），
立即返回 202；推理步骤通过 reasoning_hub 经 WS /api/reasoning/ws/{opportunity_id} 实时推送。

与聊天助手通道物理隔离：pipeline 默认纯本地规则；llm 节点(enable_llm)开启时调 LLM 抽取增强，失败自动降级规则结果，不阻塞主流程。
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
    confirm: Optional[dict] = None              # LLM 确认面板决策 {item_id: accept|ignore}


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
    if supplement_text or body.explicit_budget is not None or body.confirm:
        supplement = {
            "text": supplement_text or None,
            "budget": body.explicit_budget,
            "confirm": body.confirm or {},
        }

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


class ConfirmBody(BaseModel):
    requirement_text: str = ""
    decisions: Optional[dict] = None    # {item_id: accept|ignore}


@router.get("/llm-metrics")
def llm_metrics():
    """LLM 节点指标汇总（P3）：调用次数/平均耗时/成功率 + 反馈采纳率/修订率。

    数据源：rules.llm_trace（每次 LLM 节点调用）+ requirement_samples（llm_feedback 决策）。
    """
    from app.services.llm_trace import llm_metrics as _metrics
    return _metrics()


@router.post("/{opportunity_id}/confirm", status_code=200)
def record_confirm(opportunity_id: str, body: ConfirmBody):
    """LLM 确认面板反馈（全部采纳/部分忽略）→ rules.requirement_samples（source=llm_feedback）。

    仅记录决策，不重跑 pipeline：用于「全部采纳、直接看方案」的场景（改了决策的场景走
    generate 的 confirm 参数，由 confirm 节点应用并记录）。
    """
    from app.services.requirement_intel_service import _write_llm_feedback_sample
    decisions = body.decisions or {}
    applied = [
        {"id": k, "slot": k.removeprefix("cf_"), "decision": v, "value": v}
        for k, v in decisions.items() if v in ("accept", "ignore")
    ]
    _write_llm_feedback_sample(opportunity_id, body.requirement_text or "", applied)
    return {"status": "recorded", "count": len(applied)}


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
