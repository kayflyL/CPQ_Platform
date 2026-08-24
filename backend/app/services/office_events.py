"""Office event publishers.

Business code should call these helpers without worrying about WebSocket
connections. All publishes are best-effort and must never block/break the
existing assistant or reasoning pipelines.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from app.services.office_governance import office_governance
from app.services.office_hub import office_hub
from app.services.office_memory import office_memory


def _now() -> float:
    return time.time()


async def publish_office_event(
    role_key: Optional[str],
    status: str,
    activity: str = "",
    *,
    message: str = "",
    tool: Optional[str] = None,
    thread_id: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    zone: Optional[str] = None,
    intent: Optional[str] = None,
    participants: Optional[list] = None,
    conversation_id: Optional[str] = None,
    task_id: Optional[str] = None,
    approval_required: Optional[bool] = None,
    priority: Optional[str] = None,
    summary: Optional[str] = None,
    assignments: Optional[list] = None,
    conclusion: Optional[str] = None,
    actor: Optional[str] = None,
    source: Optional[str] = "system",
    **extra: Any,
) -> None:
    """Publish a colleague status event and update the latest snapshot."""
    try:
        payload = {
            "role_key": (role_key or "").strip() or "unknown",
            "status": status,
            "activity": activity,
            "message": message,
            "tool": tool,
            "thread_id": thread_id,
            "opportunity_id": opportunity_id,
            "zone": zone,
            "intent": intent,
            "participants": participants,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "approval_required": approval_required,
            "priority": priority,
            "summary": summary,
            "assignments": assignments,
            "conclusion": conclusion,
            "actor": actor,
            "source": source or "system",
            "ts": _now(),
            **extra,
        }
        if payload.get("approval_required"):
            await office_governance.enqueue(payload)
            return
        await office_hub.update_and_broadcast(role_key, payload)
        await office_memory.record_event(role_key, payload)
    except Exception:
        # Office visualization must never affect the business pipeline.
        pass


def schedule_office_event(
    role_key: Optional[str],
    status: str,
    activity: str = "",
    *,
    message: str = "",
    tool: Optional[str] = None,
    thread_id: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    zone: Optional[str] = None,
    intent: Optional[str] = None,
    participants: Optional[list] = None,
    conversation_id: Optional[str] = None,
    task_id: Optional[str] = None,
    approval_required: Optional[bool] = None,
    priority: Optional[str] = None,
    summary: Optional[str] = None,
    assignments: Optional[list] = None,
    conclusion: Optional[str] = None,
    actor: Optional[str] = None,
    source: Optional[str] = "system",
    **extra: Any,
) -> None:
    """Schedule an office event from a sync context, if an event loop is running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        publish_office_event(
            role_key,
            status,
            activity,
            message=message,
            tool=tool,
            thread_id=thread_id,
            opportunity_id=opportunity_id,
            zone=zone,
            intent=intent,
            participants=participants,
            conversation_id=conversation_id,
            task_id=task_id,
            approval_required=approval_required,
            priority=priority,
            summary=summary,
            assignments=assignments,
            conclusion=conclusion,
            actor=actor,
            source=source,
            **extra,
        )
    )


async def publish_pipeline_office_event(
    payload: dict,
    *,
    opportunity_id: Optional[str] = None,
    default_role_key: str = "support_engineer",
) -> None:
    """Map an existing reasoning pipeline event to an office status event."""
    try:
        event_type = payload.get("type")
        role_key = payload.get("colleague_role_key") or default_role_key
        status = "working"
        activity = ""
        message = ""
        tool = None

        if event_type == "pipeline_start":
            activity = "开始需求分析"
            message = "正在读取客户需求与推理流程"
        elif event_type == "step_start":
            label = payload.get("label") or payload.get("step") or ""
            activity = f"执行步骤：{label}"
            message = f"步骤 {payload.get('step') or ''} 已开始"
        elif event_type == "step_progress":
            sub = payload.get("sub") or {}
            kind = sub.get("kind")
            if kind == "tool":
                tool = sub.get("tool") or sub.get("name") or ""
                activity = "调用工具"
                message = sub.get("text") or tool or "正在调用工具"
            elif kind == "error":
                status = "error"
                activity = "工具执行异常"
                message = sub.get("text") or payload.get("step") or "ReAct 执行失败"
            else:
                activity = "分析中"
                message = sub.get("text") or payload.get("step") or ""
                if sub.get("tool"):
                    tool = sub.get("tool")
        elif event_type == "step_done":
            activity = "完成分析步骤"
            message = f"步骤 {payload.get('step') or ''} 已完成"
        elif event_type == "plan_progress":
            remaining = payload.get("remaining_labels") or []
            activity = "编排计划更新"
            message = "剩余：" + "、".join(str(x) for x in remaining[:5]) if remaining else "编排进行中"
        elif event_type == "business_entity_ready":
            entity_type = str(payload.get("entity_type") or "")
            activity = "生成业务草稿"
            message = "BOM 方案草稿已生成" if entity_type == "bom_scheme" else "业务草稿已生成"
        elif event_type == "need_input":
            status = "waiting_input"
            activity = "等待用户补充"
            message = payload.get("question") or "需要用户确认或补充信息"
        elif event_type == "pipeline_paused":
            status = "waiting_input"
            activity = "流程暂停"
            message = "等待用户回复后继续"
        elif event_type == "pipeline_done":
            status = "done"
            activity = "需求分析完成"
            message = "已生成配置方案"
        elif event_type == "error":
            status = "error"
            activity = "任务异常"
            message = payload.get("message") or "分析流程发生错误"
        else:
            return

        await publish_office_event(
            role_key,
            status,
            activity,
            message=message,
            tool=tool,
            thread_id=payload.get("thread_id"),
            opportunity_id=opportunity_id or payload.get("opportunity_id"),
        )
    except Exception:
        pass
