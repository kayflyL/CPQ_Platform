"""Assistant API — global AI assistant chat.

Identity resolved from X-User-Id (same as Feed). POST /threads/{id}/messages stores
the user turn and kicks off a background LLM stream; tokens are pushed over the WS
endpoint (/ws/{thread_id}) via assistant_hub. If the call fails, the real error
(HTTP/auth/model name) is surfaced in-chat so the user can diagnose; AI 设置页的
「测试连接」按钮做更结构化的排障。
"""
import asyncio
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
