"""站内通知 API — 收件箱 REST + 全局推送 WS。

WS: /api/notifications/ws?token=<JWT>，连接即推未读数快照；
后续事件 {"type":"notification","notification":{...}} 实时推送。
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.api.deps import get_current_user, resolve_ws_user
from app.repository.notification_repo import NotificationRepository
from app.services import notification_hub

router = APIRouter()


@router.get("/api/notifications")
def list_notifications(page: int = 1, page_size: int = 20,
                       unread_only: bool = False, types: str = "",
                       user: dict = Depends(get_current_user)):
    type_list = [t for t in (types or "").split(",") if t]
    repo = NotificationRepository()
    try:
        items, total = repo.list_for_user(
            user.get("user_id") or "", page=page, page_size=page_size,
            unread_only=unread_only, types=type_list)
        return {"notifications": items, "total": total}
    finally:
        repo.close()


@router.get("/api/notifications/unread-count")
def unread_count(user: dict = Depends(get_current_user)):
    repo = NotificationRepository()
    try:
        uid = user.get("user_id") or ""
        return {"count": repo.unread_count(uid), "by_type": repo.unread_by_type(uid)}
    finally:
        repo.close()


@router.post("/api/notifications/{notification_id}/read")
def mark_read(notification_id: str, user: dict = Depends(get_current_user)):
    repo = NotificationRepository()
    try:
        ok = repo.mark_read(notification_id, user.get("user_id") or "")
        if not ok:
            raise HTTPException(status_code=404, detail="通知不存在")
        return {"ok": True, "count": repo.unread_count(user.get("user_id") or "")}
    finally:
        repo.close()


@router.post("/api/notifications/read-all")
def mark_all_read(user: dict = Depends(get_current_user)):
    repo = NotificationRepository()
    try:
        n = repo.mark_all_read(user.get("user_id") or "")
        return {"ok": True, "marked": n}
    finally:
        repo.close()


@router.delete("/api/notifications/{notification_id}")
def delete_notification(notification_id: str, user: dict = Depends(get_current_user)):
    repo = NotificationRepository()
    try:
        ok = repo.delete(notification_id, user.get("user_id") or "")
        if not ok:
            raise HTTPException(status_code=404, detail="通知不存在")
        return {"ok": True, "count": repo.unread_count(user.get("user_id") or "")}
    finally:
        repo.close()


@router.post("/api/notifications/clear-read")
def clear_read(user: dict = Depends(get_current_user)):
    repo = NotificationRepository()
    try:
        n = repo.delete_read(user.get("user_id") or "")
        return {"ok": True, "deleted": n}
    finally:
        repo.close()


@router.websocket("/api/notifications/ws")
async def notifications_ws(ws: WebSocket, token: str = ""):
    user = resolve_ws_user(token)
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    notification_hub.bind_loop(asyncio.get_running_loop())
    uid = user.get("user_id") or ""
    notification_hub.connect(uid, ws)
    repo = NotificationRepository()
    try:
        await ws.send_text(json.dumps({
            "type": "unread_count",
            "count": repo.unread_count(uid),
        }))
    except Exception:
        pass
    finally:
        repo.close()
    try:
        while True:
            # 客户端消息仅作心跳占位
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notification_hub.disconnect(uid, ws)
