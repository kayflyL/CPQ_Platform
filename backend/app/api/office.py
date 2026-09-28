"""AI office API.

Read-only office visualization endpoints, persistent event history,
memory management, and the authenticated WebSocket live stream.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_current_user, require_admin, resolve_ws_user
from app.core.config import get_settings
from app.repository.office_event_repo import OfficeEventRepository
from app.services.office_access import allowed_office_role_keys
from app.services.office_events import publish_office_event
from app.services.office_governance import office_governance
from app.services.office_hub import office_hub
from app.services.office_memory import office_memory
from app.services.office_mission import cancel_mission, clear_missions, create_mission, delete_mission, get_mission, list_missions, retry_mission

router = APIRouter(prefix="/api/office", tags=["ai-office"])

class OfficeIntentRequest(BaseModel):
    role_key: str
    intent: str
    status: str = "working"
    zone: Optional[str] = None
    activity: Optional[str] = None
    message: Optional[str] = None


class GovernanceDecision(BaseModel):
    reason: Optional[str] = None


class GovernanceBatchRequest(BaseModel):
    action: str
    item_ids: list
    reason: Optional[str] = None


class MissionCreateRequest(BaseModel):
    prompt: str
    owner_role_key: Optional[str] = None
    priority: Optional[str] = "medium"
    opportunity_id: Optional[str] = None
    flow_node: Optional[str] = None
    skill_key: Optional[str] = None
    artifacts: Optional[list] = None


class MissionClearRequest(BaseModel):
    statuses: Optional[list] = None


def _merge_office_events(db_items: list, memory_items: list) -> list:
    """Merge the newest persisted page with process-local events that may not be flushed yet."""
    merged: list = []
    seen: set = set()
    for item in list(memory_items) + list(db_items):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("role_key") or ""),
            float(item.get("ts") or 0),
            str(item.get("activity") or ""),
            str(item.get("status") or ""),
            str(item.get("source") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(item))
    return sorted(merged, key=lambda item: float(item.get("ts") or 0), reverse=True)


def _repo_query(
    page: int,
    page_size: int,
    *,
    role_key: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    start_ts: Optional[float] = None,
    end_ts: Optional[float] = None,
    keyword: Optional[str] = None,
    allowed_role_keys: Optional[list] = None,
) -> dict:
    repo = OfficeEventRepository()
    return repo.query(
        page=page,
        page_size=page_size,
        role_key=role_key,
        status=status,
        source=source,
        start_ts=start_ts,
        end_ts=end_ts,
        keyword=keyword,
        allowed_role_keys=allowed_role_keys,
    )


@router.get("/snapshot")
def office_snapshot(user: dict = Depends(get_current_user)):
    """Current per-colleague office status map, scoped by the user's room access."""
    allowed = allowed_office_role_keys(user)
    return {"snapshot": office_hub.snapshot(allowed)}


@router.get("/events")
def office_events(limit: int = 100, user: dict = Depends(get_current_user)):
    """Persisted office event timeline, merged with the latest in-process events."""
    allowed = allowed_office_role_keys(user)
    result = _repo_query(1, limit, allowed_role_keys=allowed)
    events = _merge_office_events(result.get("items", []), office_memory.recent_all(limit))[:max(1, min(int(limit or 100), 300))]
    return {
        "events": events,
        "total": result.get("total", len(events)),
        "page": 1,
        "page_size": len(events),
    }


@router.post("/intent")
async def office_intent(data: OfficeIntentRequest, user: dict = Depends(get_current_user)):
    """Publish a user-directed office intent without hardcoded routes."""
    await publish_office_event(
        data.role_key,
        data.status,
        data.activity or data.message or "",
        message=data.message or "",
        zone=data.zone,
        intent=data.intent,
        priority="user",
        actor=(user or {}).get("name") or (user or {}).get("id") or "user",
        source="user",
    )
    return {"published": True, "role_key": data.role_key, "intent": data.intent}


@router.post("/missions")
async def office_create_mission(data: MissionCreateRequest, user: dict = Depends(get_current_user)):
    """Create a config-driven office mission from a natural-language instruction."""
    actor = (user or {}).get("name") or (user or {}).get("id") or "user"
    mission = create_mission(
        data.prompt,
        actor,
        data.owner_role_key,
        data.priority or "medium",
        opportunity_id=data.opportunity_id,
        flow_node=data.flow_node,
        skill_key=data.skill_key,
        artifacts=data.artifacts,
    )
    if not mission.get("ok"):
        raise HTTPException(status_code=400, detail=mission.get("error") or "任务创建失败")
    return mission


@router.get("/missions")
def office_list_missions(limit: int = 50, user: dict = Depends(get_current_user)):
    """Recent office missions."""
    return {"missions": list_missions(limit)}


@router.delete("/missions/{mission_id}")
def office_delete_mission(mission_id: str, user: dict = Depends(get_current_user)):
    if not delete_mission(mission_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"deleted": mission_id}


@router.post("/missions/clear")
def office_clear_missions(data: MissionClearRequest, user: dict = Depends(get_current_user)):
    removed = clear_missions(data.statuses)
    return {"removed": removed}


@router.post("/missions/{mission_id}/cancel")
def office_cancel_mission(mission_id: str, user: dict = Depends(get_current_user)):
    mission = cancel_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not mission.get("ok", True):
        raise HTTPException(status_code=400, detail=mission.get("error") or "当前任务状态不可取消")
    return mission


@router.post("/missions/{mission_id}/retry")
def office_retry_mission(mission_id: str, user: dict = Depends(get_current_user)):
    actor = (user or {}).get("name") or (user or {}).get("id") or "user"
    mission = retry_mission(mission_id, actor)
    if not mission:
        raise HTTPException(status_code=404, detail="任务不存在或无法重试")
    if not mission.get("ok"):
        raise HTTPException(status_code=400, detail=mission.get("error") or "任务重试失败")
    return mission


@router.get("/missions/{mission_id}")
def office_get_mission(mission_id: str, user: dict = Depends(get_current_user)):
    """Mission detail including steps and assignment status."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="任务不存在")
    return mission


@router.get("/governance")
def office_governance_list(
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Pending/resolved approval queue."""
    return {"items": office_governance.list_items(status)}


@router.get("/reports/{object_id}/download")
def download_office_report(
    object_id: str,
    token: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """输出节点文件产物（office 中立桶）下载。

    鉴权双通道：axios 走 Authorization 头；iframe / window.open 直链走 ?token=
    （否则 AUTH_ENABLED 下 401）。object_id 白名单校验防路径穿越。
    """
    if get_settings().AUTH_ENABLED:
        from app.api.deps import _extract_bearer
        tok = _extract_bearer(authorization) or (token or "").strip()
        if not tok or not resolve_ws_user(tok):
            raise HTTPException(status_code=401, detail="未登录或登录已过期")
    import re as _re
    if not _re.fullmatch(r"[\w一-鿿\-]+", object_id or ""):
        raise HTTPException(status_code=404, detail="报告不存在")
    from app.services.report_pdf import OFFICE_REPORTS_DIR
    from app.services.storage_adapter import get_storage
    local = get_storage().resolve_local_path(f"{OFFICE_REPORTS_DIR}/{object_id}.pdf")
    if not local:
        raise HTTPException(status_code=404, detail="报告不存在或已清理")
    return FileResponse(path=str(local), filename=f"{object_id}.pdf",
                        media_type="application/pdf")


@router.post("/governance/batch")
async def office_governance_batch(
    data: GovernanceBatchRequest,
    admin: dict = Depends(require_admin),
):
    """Batch approve or reject governance items."""
    action = (data.action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action 仅支持 approve 或 reject")
    item_ids = [str(item_id).strip() for item_id in (data.item_ids or []) if str(item_id).strip()]
    if not item_ids:
        raise HTTPException(status_code=400, detail="item_ids 不能为空")

    actor = (admin or {}).get("name") or (admin or {}).get("id") or "admin"
    processed: list = []
    skipped: list = []
    failed: list = []

    for item_id in item_ids:
        try:
            if action == "approve":
                item = await office_governance.approve(item_id, actor)
            else:
                item = await office_governance.reject(item_id, actor, data.reason or "")
            processed.append(item)
        except KeyError:
            failed.append({"item_id": item_id, "error": "审批项不存在"})
        except ValueError as exc:
            skipped.append({"item_id": item_id, "error": str(exc)})

    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "total_requested": len(item_ids),
    }


@router.post("/governance/{item_id}/approve")
async def office_governance_approve(
    item_id: str,
    decision: Optional[GovernanceDecision] = None,
    admin: dict = Depends(require_admin),
):
    """Approve an approval-required office event."""
    try:
        item = await office_governance.approve(item_id, (admin or {}).get("name") or (admin or {}).get("id") or "admin")
    except KeyError:
        raise HTTPException(status_code=404, detail="审批项不存在")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"item": item}


@router.post("/governance/{item_id}/reject")
async def office_governance_reject(
    item_id: str,
    decision: Optional[GovernanceDecision] = None,
    admin: dict = Depends(require_admin),
):
    """Reject an approval-required office event."""
    try:
        item = await office_governance.reject(
            item_id,
            (admin or {}).get("name") or (admin or {}).get("id") or "admin",
            reason=(decision.reason if decision else None) or "",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="审批项不存在")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"item": item}


@router.websocket("/ws")
async def office_ws(ws: WebSocket):
    """Authenticated office stream: filtered snapshot first, then live status events."""
    user = resolve_ws_user(ws.query_params.get("token"))
    if get_settings().AUTH_ENABLED and not user:
        await ws.close(code=4401)
        return

    allowed = allowed_office_role_keys(user)
    await office_hub.connect(ws, allowed)
    try:
        await ws.send_json({"type": "snapshot", "snapshot": office_hub.snapshot(allowed)})
        while True:
            message_text = await ws.receive_text()
            if message_text.strip() == '{"type":"ping"}' or '"type":"ping"' in message_text:
                await ws.send_json({"type": "pong", "ts": __import__("time").time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await office_hub.disconnect(ws)
