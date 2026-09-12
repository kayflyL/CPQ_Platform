# -*- coding: utf-8 -*-
"""AI 同事回合的「落库 / 广播 / 溯源」层。

从 colleague_turn_service.py 拆出（2026-09-11，零行为改动）：回合结果如何持久化、
如何广播给前端、如何写 trace、以及 AI 办公室会话的隐藏商机从哪来。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.repository.assistant_repo import AssistantRepository
from app.services.assistant_hub import assistant_hub
from app.services.office_events import publish_office_event

logger = logging.getLogger(__name__)


async def _persist_and_broadcast(
    thread_id: str,
    colleague: Optional[dict],
    final_text: str,
    *,
    final_office_event: Optional[dict] = None,
) -> None:
    role_key = (colleague or {}).get("role_key") or "assistant"
    repo = AssistantRepository()
    try:
        asst = repo.add_message(
            thread_id=thread_id,
            role="assistant",
            content=final_text,
            colleague_role_key=(colleague or {}).get("role_key"),
        )
    except Exception:
        logger.exception("colleague reply persistence failed")
        asst = None
    finally:
        repo.close()
    await assistant_hub.broadcast(thread_id, {"type": "done", "message": asst})

    if final_office_event:
        try:
            await publish_office_event(
                final_office_event.get("role_key") or role_key,
                final_office_event.get("status") or "done",
                final_office_event.get("activity") or "回复完成",
                message=final_office_event.get("message") or final_text[:160],
                zone=final_office_event.get("zone"),
                intent=final_office_event.get("intent"),
                thread_id=thread_id,
                priority="user",
                source="assistant_chat",
            )
        except Exception:
            logger.exception("final office event publish failed")


def _add_assistant_message(
    thread_id: str,
    colleague: Optional[dict],
    content: str,
    *,
    kind: str = "text",
    data: Optional[str] = None,
) -> Optional[dict]:
    """把结构化 AI 回复落进 assistant 会话，供所有聊天入口重放。"""
    repo = AssistantRepository()
    try:
        return repo.add_message(
            thread_id=thread_id,
            role="assistant",
            content=content,
            kind=kind,
            data=data,
            colleague_role_key=(colleague or {}).get("role_key"),
        )
    except Exception:
        logger.exception("colleague structured message persistence failed")
        return None
    finally:
        repo.close()


async def _trace(trace_sink: Optional[Callable[..., None]], **kwargs: Any) -> None:
    if not trace_sink:
        return
    try:
        trace_sink(**kwargs)
    except Exception:
        logger.exception("colleague turn trace failed")


def _ensure_ai_office_opportunity(
    thread_id: str,
    user: Optional[dict],
    requirement_text: str,
) -> str:
    """为 AI Office 会话创建一条隐藏的内部商机，用于承载真实四步表单数据。"""
    import uuid

    from app.repository.opportunity_repo import OpportunityRepository

    user_name = str((user or {}).get("name") or (user or {}).get("user_id") or "用户").strip() or "用户"
    snippet = (requirement_text or "").strip().replace("\n", " ")[:24] or "AI 办公室会话"
    opportunity_id = f"ai-{uuid.uuid4().hex[:24]}"

    opp_repo = OpportunityRepository()
    try:
        opp_repo.create_or_update_opportunity(
            opportunity_id,
            {
                "customer_name": f"{user_name} · {snippet}",
                "sales_person": user_name,
                "owner_user_id": str((user or {}).get("user_id") or "") or None,
                "fae": "",
                "quotation_person": "",
                "industry": "",
                "order_type": "",
            },
        )
        # 内部商机暂不进入「我的商机列表」；转真实商机时再改为 active。
        opp_repo.update_meta(opportunity_id, {"status": "ai_office"})
    finally:
        opp_repo.close()

    repo = AssistantRepository()
    try:
        repo.update_thread_opportunity_id(thread_id, opportunity_id)
    finally:
        repo.close()
    return opportunity_id
