"""Assistant API — global AI assistant chat.

Identity resolved from X-User-Id (same as Feed). POST /threads/{id}/messages stores
the user turn and kicks off a background LLM stream; tokens are pushed over the WS
endpoint (/ws/{thread_id}) via assistant_hub. If the call fails, the real error
(HTTP/auth/model name) is surfaced in-chat so the user can diagnose; AI 设置页的
「测试连接」按钮做更结构化的排障。
"""
import asyncio
import logging
import json
from typing import Optional

from fastapi import (
    APIRouter, Header, HTTPException, Depends, WebSocket, WebSocketDisconnect,
)
from pydantic import BaseModel

from app.repository.assistant_repo import AssistantRepository
from app.repository.feed_user_repo import FeedUserRepository
from app.services import llm_client
from app.services.assistant_hub import assistant_hub
from app.services.llm_client import LLMError
from app.services.requirement_intel_service import run_assistant_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def current_user(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")) -> dict:
    """Resolve acting user from X-User-Id, falling back to 匿名 (mirrors Feed)."""
    repo = FeedUserRepository()
    try:
        if x_user_id:
            u = repo.get(x_user_id)
            if u:
                return u
        return repo.get_or_create("匿名")
    finally:
        repo.close()


class CreateThreadBody(BaseModel):
    title: Optional[str] = None
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None


class PostMessageBody(BaseModel):
    content: str
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None
    context_summary: Optional[str] = None  # 前端多域 provider 拼的当前上下文摘要


class AnalyzeBody(BaseModel):
    """方案助手「需求分析 → 生成 BOM」入参（与商机详情页 generate 同语义）。

    requirement_text: 本轮需求/补充文本；supplement_text: 反问补充（续接暂停的 pipeline）；
    explicit_budget / force_complete / confirm 与商机通道一致。
    """
    requirement_text: str = ""
    supplement_text: Optional[str] = None
    explicit_budget: Optional[float] = None
    force_complete: bool = False
    confirm: Optional[dict] = None


@router.post("/threads")
def create_thread(body: CreateThreadBody, user: dict = Depends(current_user)):
    repo = AssistantRepository()
    try:
        return {"thread": repo.create_thread(
            created_by=user["user_id"],
            title=body.title,
            opportunity_id=body.opportunity_id,
            quotation_id=body.quotation_id,
        )}
    finally:
        repo.close()


@router.get("/threads")
def list_threads(user: dict = Depends(current_user)):
    repo = AssistantRepository()
    try:
        return {"threads": repo.list_threads(user["user_id"])}
    finally:
        repo.close()


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: str):
    repo = AssistantRepository()
    try:
        if not repo.get_thread(thread_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"messages": repo.list_messages(thread_id)}
    finally:
        repo.close()


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: PostMessageBody, user: dict = Depends(current_user)):
    """Append a user turn, then stream an assistant reply via WS.

    立即返回 user_message;LLM token 流通过 /ws/{thread_id} 推送(chunk → done)。
    首条用户消息自动作为会话标题。LLM 失败时回退占位回复。
    """
    repo = AssistantRepository()
    try:
        thread = repo.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="会话不存在")
        user_msg = repo.add_message(
            thread_id=thread_id, role="user", content=body.content,
            opportunity_id=body.opportunity_id, quotation_id=body.quotation_id,
        )
        # auto-title: 首条用户消息前 24 字作为标题
        if not thread.get("title") or thread["title"] == "新会话":
            snippet = (body.content or "").strip().replace("\n", " ")[:24]
            if snippet:
                updated = repo.update_thread_title(thread_id, snippet)
                if updated:
                    thread = updated
        history = repo.list_messages(thread_id)
    finally:
        repo.close()

    asyncio.create_task(_stream_llm_reply(thread_id, body.content, body.context_summary, history))
    return {"user_message": user_msg, "thread": thread}


@router.post("/threads/{thread_id}/analyze", status_code=202)
async def analyze_thread(thread_id: str, body: AnalyzeBody, user: dict = Depends(current_user)):
    """方案助手通道需求分析：与商机详情页同一套 pipeline（图驱动 executor + 反问 + LLM 增强 +
    BOM 组合），状态存 assistant 会话、步骤/方案经 /ws/{thread_id} 流式推送。

    立即返回 202；前端订阅助手 WS 消费 pipeline_start/step_*/need_input/need_confirm/
    candidates_ready/pipeline_done|paused/analysis_result 事件。
    补充分支：supplement_text 续接暂停的 pipeline（同商机通道反答回填语义）。
    """
    repo = AssistantRepository()
    try:
        thread = repo.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="会话不存在")
        text = (body.requirement_text or "").strip()
        supplement_text = (body.supplement_text or "").strip()
        # 反答/跳过时前端不重发原文：从会话状态取已存的需求原文（与商机详情页传原文+补充同语义）
        if not text and (supplement_text or body.force_complete):
            try:
                from app.services.reasoning_session import ReasoningSession
                extra = ReasoningSession(thread_id, "thread").get_extra()
                text = (extra.get("requirement_clarity_base") or "").strip()
            except Exception:
                text = ""
        if not text and not supplement_text:
            raise HTTPException(status_code=400, detail="需求内容为空")
        # 需求文本作为用户消息入库（kind=analysis_trigger），历史重放/身份归属用
        user_msg = repo.add_message(
            thread_id=thread_id, role="user",
            content=text or f"[补充] {supplement_text}",
            opportunity_id=thread.get("opportunity_id") or None,
            kind="analysis_trigger",
            data=json.dumps({"supplement": bool(supplement_text)}, ensure_ascii=False),
        )
        # auto-title：首条消息前 24 字
        if not thread.get("title") or thread["title"] == "新会话":
            snippet = (text or supplement_text or "").strip().replace("\n", " ")[:24]
            if snippet:
                updated = repo.update_thread_title(thread_id, snippet)
                if updated:
                    thread = updated
    finally:
        repo.close()

    asyncio.create_task(_stream_analysis(
        thread_id, text, supplement_text,
        body.explicit_budget, body.force_complete, body.confirm,
    ))
    return {"status": "started", "thread_id": thread_id, "user_message": user_msg}


def _fmt_money(v) -> str:
    """金额格式化（¥1,234.56）；非数字回落 '-'。"""
    try:
        return f"¥{float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _plan_bom_text(plan: dict) -> str:
    """把单个整机方案转成可读 BOM 文本（L6 配置单 + KP 配置单）。

    供对话框/企业微信直接展示：纯文本 + 管道分隔，不依赖组件渲染。
    """
    cfg = plan.get("cfg") or {}
    rows = cfg.get("bom_excel_rows") or []
    l6 = [r for r in rows if r.get("category") == "L6"]
    kp = [r for r in rows if r.get("category") == "Key Parts"]
    head = " · ".join([
        x for x in [
            plan.get("series"),
            plan.get("form"),
            f"{plan.get('bays')}盘位" if plan.get("bays") is not None else None,
        ] if x
    ]) or "整机方案"
    summary = plan.get("summary") or {}
    out = [
        f"{plan.get('name') or plan.get('model') or '整机方案'}（{head}）",
        f"总价 {_fmt_money(summary.get('total_cost'))} · 底盘 {summary.get('parts_count', 0)} 件 + KP {summary.get('kp_count', 0)} 件",
    ]
    if l6:
        out.append("")
        out.append("— L6 配置单 —")
        out.append("Catalogue | Description | Qty")
        for r in l6:
            out.append(f"{r.get('catalogue') or ''} | {r.get('description') or ''} | {r.get('qty') or ''}")
    if kp:
        out.append("")
        out.append("— KP 配置单 —")
        out.append("Catalogue | Description | Qty | 单价")
        for r in kp:
            out.append(f"{r.get('catalogue') or ''} | {r.get('description') or ''} | {r.get('qty') or ''} | {_fmt_money(r.get('base_price'))}")
    return "\n".join(out)


def _build_bom_text(plans: list) -> str:
    """多个方案拼成一段可读 BOM 文本（对话框/企微推送用）。"""
    return "\n\n".join(f"【{i}】{_plan_bom_text(p)}" for i, p in enumerate(plans, 1))


async def _stream_analysis(
    thread_id: str, requirement_text: str, supplement_text: Optional[str],
    budget: Optional[float], force_complete: bool, confirm: Optional[dict],
) -> None:
    """跑方案助手需求分析 pipeline，并把结果/暂停点落库为结构化消息（历史重放）。

    事件经 assistant_hub 广播给 /ws/{thread_id} 的实时客户端；结束后按终态补一条
    analysis_result / analysis_pending / analysis_confirm 消息，供刷新后重放方案卡/反问框。
    """
    supplement = None
    if supplement_text or budget is not None or confirm:
        supplement = {"text": supplement_text or None, "budget": budget, "confirm": confirm or {}}

    events: list = []
    try:
        events = await run_assistant_pipeline(
            thread_id, requirement_text,
            supplement=supplement, force_complete=force_complete,
        )
    except Exception as e:
        logger.exception("方案助手需求分析失败 thread=%s", thread_id)
        final_text = f"⚠️ 需求分析失败：{e}"
        await assistant_hub.broadcast(thread_id, {"type": "error", "message": final_text})
        repo = AssistantRepository()
        try:
            repo.add_message(thread_id=thread_id, role="assistant", content=final_text)
        finally:
            repo.close()
        return

    # 从事件流提取终态：最后一条 need_input/need_confirm + candidates_ready 方案
    plans: list = []
    keywords: list = []
    series = None
    form = None
    last_input: Optional[dict] = None
    last_confirm: Optional[dict] = None
    for ev in events:
        t = ev.get("type")
        if t == "candidates_ready":
            plans = ev.get("plans") or []
            keywords = ev.get("keywords") or []
            series = ev.get("series")
            form = ev.get("form")
        elif t == "need_input":
            last_input = {
                "question": ev.get("question") or "",
                "options": ev.get("options") or [],
                "reply_id": ev.get("reply_id") or "",
                "stage": ev.get("stage") or "",
                "format": ev.get("format") or "",
                "round": ev.get("round") or 1,
                "clarity_capped": bool(ev.get("clarity_capped")),
            }
        elif t == "need_confirm":
            last_confirm = {
                "question": ev.get("question") or "",
                "items": ev.get("items") or [],
                "default": ev.get("default") or "accept",
                "reply_id": ev.get("reply_id") or "",
            }

    repo = AssistantRepository()
    try:
        if plans:
            names = [p.get("name") or p.get("model") or p.get("config_id") for p in plans]
            bom_text = _build_bom_text(plans)
            summary = (
                "✅ 需求分析完成，生成 %d 个整机方案：\n%s\n\n%s"
                % (len(plans), "\n".join(f"- {n}" for n in names), bom_text)
            )
            result_msg = repo.add_message(
                thread_id=thread_id, role="assistant", content=summary,
                kind="analysis_result",
                data=json.dumps({
                    "plans": plans, "keywords": keywords, "series": series, "form": form,
                    "bom_text": bom_text,
                }, ensure_ascii=False, default=str),
            )
            # 广播结果消息：实时网页端也把 BOM 文本气泡推进对话流（与企微端推送同一段文本）
            await assistant_hub.broadcast(thread_id, {
                "type": "analysis_result",
                "message": result_msg,
                "data": {"bom_text": bom_text},
            })
        elif last_input:
            q = last_input["question"] or "请补充以下信息："
            options = "（可选：%s）" % " / ".join(last_input["options"]) if last_input.get("options") else ""
            repo.add_message(
                thread_id=thread_id, role="assistant", content=f"{q}{options}",
                kind="analysis_pending",
                data=json.dumps(last_input, ensure_ascii=False, default=str),
            )
        elif last_confirm:
            repo.add_message(
                thread_id=thread_id, role="assistant", content=last_confirm["question"] or "大模型补充了信息，请确认：",
                kind="analysis_confirm",
                data=json.dumps(last_confirm, ensure_ascii=False, default=str),
            )
        else:
            repo.add_message(
                thread_id=thread_id, role="assistant",
                content="需求分析未生成方案，请补充需求后重试。",
            )
    finally:
        repo.close()
    # 广播一个终态事件，让实时 UI 收尾（WS 已收到全部事件，此事件仅兜底/定稿用）
    await assistant_hub.broadcast(thread_id, {"type": "analysis_finished"})


async def _stream_llm_reply(
    thread_id: str, user_text: str, context_summary: Optional[str], history: list
) -> None:
    """Stream the assistant reply to all WS clients on this thread; persist on done.

    Falls back to a placeholder if DASHSCOPE_API_KEY is unset or the call fails,
    so the chat flow stays usable even before/without a configured model.

    Note: llm_client.stream_chat will auto-inject system_prompt from config.
    """
    # 构建消息列表（llm_client 会自动添加 system prompt）
    messages: list = []

    # 如果有上下文，作为第一条 user 消息
    if context_summary:
        messages.append({"role": "user", "content": f"[当前上下文]\n{context_summary}"})
        messages.append({"role": "assistant", "content": "收到，我会基于这个上下文作答。"})

    # 添加历史消息
    for m in history:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # 添加当前用户消息
    messages.append({"role": "user", "content": user_text})

    full: list = []
    try:
        async for delta in llm_client.stream_chat(messages):
            full.append(delta)
            await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": delta})
        final_text = "".join(full) or "(空回复)"
    except LLMError as e:
        # 透传真实错误（HTTP 状态/鉴权/model 名等），不再用占位文案吞掉；
        # AI 设置页的「测试连接」按钮可做更结构化的排障。
        final_text = (
            f"⚠️ 模型调用失败：{e}\n\n"
            "请到「AI 设置 → API 设置」检查端点 / Key / 模型名，"
            "可用「测试连接」按钮定位具体原因。"
        )
        await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": final_text})

    repo = AssistantRepository()
    try:
        asst = repo.add_message(thread_id=thread_id, role="assistant", content=final_text)
    finally:
        repo.close()
    await assistant_hub.broadcast(thread_id, {"type": "done", "message": asst})


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    repo = AssistantRepository()
    try:
        ok = repo.soft_delete_thread(thread_id)
        if not ok:
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        repo.close()
    return {"status": "ok"}


# ── WS: subscribe to a thread's LLM token stream ──

@router.websocket("/ws/{thread_id}")
async def assistant_ws(ws: WebSocket, thread_id: str):
    """Subscribe to the thread's token stream (chunk / done broadcast by _stream_llm_reply).

    Frontend connects on panel open + currentThreadId. Inbound text is ignored
    (user messages go via REST POST which triggers the stream).
    """
    await assistant_hub.connect(ws, thread_id)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await assistant_hub.disconnect(ws)
