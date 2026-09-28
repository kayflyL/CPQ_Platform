"""通知中心 hub — WS 连接登记 + 跨线程推送 + notify_users 落库+推送。

流程端点大多是 sync def（FastAPI 线程池执行），WS 在事件循环里：
push() 用 run_coroutine_threadsafe 把发送动作调度回主循环。
"""
import asyncio
import json
from typing import Iterable, List, Optional

from fastapi import WebSocket

_loop: Optional[asyncio.AbstractEventLoop] = None
_clients: dict = {}  # user_id -> set[WebSocket]


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def connect(user_id: str, ws: WebSocket) -> None:
    _clients.setdefault(user_id, set()).add(ws)


def disconnect(user_id: str, ws: WebSocket) -> None:
    conns = _clients.get(user_id)
    if conns:
        conns.discard(ws)
        if not conns:
            _clients.pop(user_id, None)


async def _send(user_id: str, payload: dict) -> None:
    for ws in list(_clients.get(user_id) or ()):
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            disconnect(user_id, ws)


def push(user_ids: Iterable[str], payload: dict) -> None:
    """线程安全推送：任意线程可调，无连接/无循环时静默跳过。"""
    if not _loop or _loop.is_closed():
        return
    for uid in {u for u in user_ids if u}:
        try:
            asyncio.run_coroutine_threadsafe(_send(uid, payload), _loop)
        except RuntimeError:
            return


def notify_users(user_ids: Iterable[str], type: str, title: str, body: str = "",
                 opportunity_id: str = "", payload: Optional[dict] = None,
                 exclude_user_id: str = "") -> List[dict]:
    """落库 + 实时推送。去重、剔除空值与触发者本人；失败只打印不抛（通知不能阻断流程）。"""
    from app.repository.notification_repo import NotificationRepository
    uniq = [u for u in dict.fromkeys(user_ids) if u and u != exclude_user_id]
    if not uniq:
        return []
    repo = NotificationRepository()
    created = []
    try:
        for uid in uniq:
            try:
                created.append(repo.create(
                    uid, type, title, body,
                    opportunity_id=opportunity_id, payload=payload,
                ))
            except Exception as exc:
                print(f"⚠️ notification insert failed: {exc}")
    finally:
        repo.close()
    if created:
        item = created[0]
        push([c["user_id"] for c in created], {
            "type": "notification",
            "notification": {
                "notification_id": item["notification_id"],
                "type": item["type"],
                "title": item["title"],
                "body": item["body"],
                "opportunity_id": item["opportunity_id"],
                "created_at": item["created_at"],
            },
        })
    return created
