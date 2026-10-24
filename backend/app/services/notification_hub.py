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
_presence: dict = {}  # user_id -> {"name": str, "role": str}（有连接期间维护）


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def connect(user_id: str, ws: WebSocket, name: str = "", role: str = "") -> bool:
    """登记连接。返回该用户是否首连（多标签页只算一次上线）。"""
    first = user_id not in _clients
    _clients.setdefault(user_id, set()).add(ws)
    _presence[user_id] = {"name": name or user_id, "role": role or "member"}
    return first


def disconnect(user_id: str, ws: WebSocket) -> bool:
    """移除连接。返回该用户是否已完全离线。"""
    conns = _clients.get(user_id)
    if conns:
        conns.discard(ws)
        if not conns:
            _clients.pop(user_id, None)
    offline = not _clients.get(user_id)
    if offline:
        _presence.pop(user_id, None)
    return offline


def online_user_ids() -> set:
    return {uid for uid, conns in _clients.items() if conns}


def build_roster() -> List[dict]:
    """全员名册（仅 active 用户）+ 在线标记，在线者置顶。角色名由 rules.roles 解析。"""
    from app.repository.feed_user_repo import FeedUserRepository
    from app.repository.role_repo import RoleRepository

    user_repo = FeedUserRepository()
    try:
        users = user_repo.list_all()
    finally:
        user_repo.close()
    role_repo = RoleRepository()
    try:
        role_names = {r["role_key"]: (r.get("name") or r["role_key"]) for r in role_repo.list_all()}
    finally:
        role_repo.close()

    online = online_user_ids()
    roster = []
    for u in users:
        if not u.get("is_active", True):
            continue
        uid = u.get("user_id") or ""
        role_key = u.get("role") or "member"
        roster.append({
            "user_id": uid,
            "name": u.get("name") or "匿名",
            "role_key": role_key,
            "role_name": role_names.get(role_key, role_key),
            "online": uid in online,
        })
    roster.sort(key=lambda x: (not x["online"], x["name"]))
    return roster


async def broadcast_presence() -> None:
    """向所有在线连接广播全员名册；发送失败的连接顺手清册。"""
    payload = json.dumps({"type": "presence", "users": build_roster()}, ensure_ascii=False)
    for uid, conns in list(_clients.items()):
        for ws in list(conns):
            try:
                await ws.send_text(payload)
            except Exception:
                disconnect(uid, ws)


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
        _relay_wecom([c["user_id"] for c in created], type, title, body)
    return created


def _relay_wecom(user_ids: List[str], type: str, title: str, body: str = "") -> None:
    """企微外推：应用通道按 wecom_userid 映射(收件人视角原文)；
    群机器人是全员广播，站内的「你」在群里没有指代，
    按类型改写成第三人称播报并点出收件人。失败只打日志。"""
    try:
        from app.repository.feed_user_repo import FeedUserRepository
        from app.services.wecom_client import enqueue_text, enqueue_webhook
        repo = FeedUserRepository()
        try:
            names_map = repo.name_map(user_ids)
            wecom_map = repo.wecom_map(user_ids)
        finally:
            repo.close()
        name_list = [names_map[u] for u in user_ids if u in names_map]
        names = "、".join(name_list)
        mentioned = [wecom_map[u] for u in user_ids if u in wecom_map]
        content = f"{title}\n{body}" if body else title
        if type == "task_assigned":
            # 「你有新任务：XX」→ 群播报「@张三 有新任务：XX」；
            # 收件人配了企微ID时 mentioned_list 真@高亮，未配只是文字@
            at = " ".join(f"@{nm}" for nm in name_list)
            group = title.replace("你有新任务：", f"{at} 有新任务：", 1) if at else title
            group = f"{group}\n{body}" if body else group
        elif type == "comment_mention":
            # 「张三 在商机「XX」的评论中@了你」→ 群播报 @被提人 + 标题 + 正文节选
            at = " ".join(f"@{nm}" for nm in name_list)
            group = f"{at} {title}" if at else title
            group = f"{group}\n{body}" if body else group
        else:
            group = f"{content}\n（通知：{names}）" if names else content
        if mentioned:
            enqueue_text(mentioned, content)
        enqueue_webhook(group, mentioned=mentioned)
    except Exception as exc:
        print(f"⚠️ wecom relay failed: {exc}")
