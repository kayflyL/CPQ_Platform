"""Opportunity collaboration feed API.

Unified activity stream: chat messages that may carry file attachments, plus a
file index view over the same attachments table. Replaces the old split
(/api/comments + /api/opportunities/{}/files).

Identity is resolved from the X-User-Id header (set by the frontend user
picker). The dependency falls back to an anonymous user so the API stays
usable before a user is picked.
"""
from typing import List, Optional
from pathlib import Path
import uuid

from fastapi import (
    APIRouter, UploadFile, File, Form, Header, HTTPException, Depends,
    WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import json

from app.repository.feed_repo import FeedRepository
from app.repository.feed_user_repo import FeedUserRepository
from app.services.storage_adapter import get_storage, build_object_id, StorageError
from app.services.feed_hub import hub

router = APIRouter(prefix="/api/feed", tags=["feed"])

# ── upload guards ──
_ALLOWED_EXTS = {
    ".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".txt", ".zip",
}
_MAX_SIZE = 50 * 1024 * 1024  # 50 MB


def current_user(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")) -> dict:
    """Resolve the acting user from X-User-Id, falling back to 匿名."""
    repo = FeedUserRepository()
    try:
        if x_user_id:
            u = repo.get(x_user_id)
            if u:
                return u
        return repo.get_or_create("匿名")
    finally:
        repo.close()


# ── users (lightweight identity) ──

@router.get("/users")
def list_users():
    repo = FeedUserRepository()
    try:
        return {"users": repo.list_all()}
    finally:
        repo.close()


class EnsureUserBody(BaseModel):
    name: str
    email: Optional[str] = None


@router.post("/users")
def ensure_user(body: EnsureUserBody):
    """Get-or-create a user by display name. Returns the user (id persisted client-side)."""
    repo = FeedUserRepository()
    try:
        return repo.get_or_create(body.name, body.email)
    finally:
        repo.close()


# ── messages ──

@router.get("/{opportunity_id}/messages")
def list_messages(opportunity_id: str):
    repo = FeedRepository()
    try:
        return {"messages": repo.list_messages(opportunity_id)}
    finally:
        repo.close()


@router.post("/{opportunity_id}/messages")
async def post_message(
    opportunity_id: str,
    body: str = Form(default=""),
    files: List[UploadFile] = File(default=[]),
    user: dict = Depends(current_user),
):
    """Post a chat message with optional attachments.

    Multipart: `body` (text, optional) + `files` (0..N). A pure comment has no
    files; a file-only drop still creates a message row anchoring the files.
    """
    body_text = (body or "").strip()
    if not body_text and not files:
        raise HTTPException(status_code=400, detail="消息内容和文件不能同时为空")

    repo = FeedRepository()
    storage = get_storage()
    try:
        msg = repo.add_message(
            opportunity_id=opportunity_id,
            author_user_id=user["user_id"],
            body=body_text or None,
            kind="comment",
        )
        saved = []
        for f in files:
            att = await _save_upload(repo, storage, f, opportunity_id, user["user_id"], msg["message_id"])
            saved.append(att)

        messages = repo.list_messages(opportunity_id)
        created = next((m for m in messages if m["message_id"] == msg["message_id"]), msg)
        await hub.broadcast(opportunity_id, {"type": "message", "message": created})
        return {"message": created}
    finally:
        repo.close()


@router.delete("/messages/{message_id}")
async def delete_message(message_id: str):
    repo = FeedRepository()
    try:
        opp = repo.soft_delete_message(message_id)
        if not opp:
            raise HTTPException(status_code=404, detail="消息不存在")
    finally:
        repo.close()
    await hub.broadcast(opp, {"type": "delete_message", "message_id": message_id})
    return {"status": "ok"}


# ── attachments ──

@router.get("/{opportunity_id}/attachments")
def list_attachments(opportunity_id: str):
    repo = FeedRepository()
    try:
        return {"attachments": repo.list_attachments(opportunity_id)}
    finally:
        repo.close()


@router.post("/{opportunity_id}/attachments")
async def upload_attachment(
    opportunity_id: str,
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    quotation_id: Optional[str] = Form(default=None),
    kind: Optional[str] = Form(default=None),
    user: dict = Depends(current_user),
):
    """Upload a single file straight to the file index (no message).

    Optional category (requirement/technical/sent_quote) drives the archive
    view; kind overrides the default 'upload' (e.g. 'export' for archived
    quotations). Sent-quote archives also emit a system activity message.
    """
    repo = FeedRepository()
    storage = get_storage()
    try:
        att = await _save_upload(
            repo, storage, file, opportunity_id, user["user_id"],
            message_id=None,
            kind=kind or "upload",
            quotation_id=quotation_id,
            category=category,
        )
        if category == "sent_quote":
            sys_msg = repo.add_message(
                opportunity_id=opportunity_id,
                author_user_id=user["user_id"],
                body=f"归档已发报价 {att['original_filename']}",
                kind="system",
                quotation_id=quotation_id,
            )
            await hub.broadcast(opportunity_id, {"type": "message", "message": sys_msg})
        await hub.broadcast(opportunity_id, {"type": "attachment", "attachment": att})
        return {"attachment": att}
    finally:
        repo.close()


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str):
    repo = FeedRepository()
    try:
        att = repo.get_attachment(attachment_id)
    finally:
        repo.close()
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    storage = get_storage()
    local = storage.resolve_local_path(att["storage_key"])
    if local:
        return FileResponse(path=str(local), filename=att["original_filename"], media_type="application/octet-stream")
    url = storage.presigned_url(att["storage_key"])
    if url:
        return RedirectResponse(url)
    raise HTTPException(status_code=404, detail="文件不可访问")


@router.get("/attachments/{attachment_id}/versions")
def attachment_versions(attachment_id: str):
    repo = FeedRepository()
    try:
        att = repo.get_attachment(attachment_id)
        if not att:
            raise HTTPException(status_code=404, detail="附件不存在")
        return {"versions": repo.list_versions(att["version_group"]), "current": att}
    finally:
        repo.close()


@router.post("/attachments/{attachment_id}/version")
async def add_attachment_version(
    attachment_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    """Re-upload a new version of an existing file (keeps history)."""
    repo = FeedRepository()
    storage = get_storage()
    try:
        existing = repo.get_attachment(attachment_id)
        if not existing:
            raise HTTPException(status_code=404, detail="附件不存在")
        next_ver = (repo.latest_version(existing["version_group"]) or 0) + 1
        att = await _save_upload(
            repo, storage, file,
            opportunity_id=existing["opportunity_id"],
            uploader_user_id=user["user_id"],
            message_id=None,
            kind="upload",
            quotation_id=existing["quotation_id"] or None,
            version=next_ver,
            version_group=existing["version_group"],
            original_name_override=existing["original_filename"],
            category=existing.get("category"),
        )
        return {"attachment": att}
    finally:
        repo.close()


class UpdateCategoryBody(BaseModel):
    category: Optional[str] = None


@router.patch("/attachments/{attachment_id}/category")
async def update_attachment_category(attachment_id: str, body: UpdateCategoryBody):
    """Move an attachment between archive buckets (requirement/technical/sent_quote)."""
    repo = FeedRepository()
    try:
        att = repo.update_attachment_category(attachment_id, body.category)
        if not att:
            raise HTTPException(status_code=404, detail="附件不存在")
    finally:
        repo.close()
    await hub.broadcast(att["opportunity_id"], {"type": "attachment", "attachment": att})
    return {"attachment": att}


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(attachment_id: str):
    repo = FeedRepository()
    try:
        opp = repo.soft_delete_attachment(attachment_id)
        if not opp:
            raise HTTPException(status_code=404, detail="附件不存在")
    finally:
        repo.close()
    await hub.broadcast(opp, {"type": "delete_attachment", "attachment_id": attachment_id})
    return {"status": "ok"}


# ── shared upload helper ──

async def _save_upload(
    repo: FeedRepository,
    storage,
    f: UploadFile,
    opportunity_id: str,
    uploader_user_id: str,
    message_id: Optional[str],
    kind: str = "upload",
    quotation_id: Optional[str] = None,
    version: int = 1,
    version_group: Optional[str] = None,
    original_name_override: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    original = original_name_override or (f.filename or "file")
    ext = Path(original).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    content = await f.read()
    if len(content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"文件过大，最大 {_MAX_SIZE // (1024 * 1024)}MB")

    # 获取商机客户名用于文件夹命名
    from app.repository.opportunity_repo import OpportunityRepository
    opp_repo = OpportunityRepository()
    try:
        opp = opp_repo.get_opportunity(opportunity_id)
        customer_name = opp.get("customer_name", "") if opp else ""
    finally:
        opp_repo.close()

    object_id = build_object_id(original)
    try:
        storage_key = storage.save_bytes(opportunity_id, object_id, content, ext, customer_name)
    except StorageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    mime = f.content_type or _guess_mime(ext)
    return repo.add_attachment(
        opportunity_id=opportunity_id,
        uploader_user_id=uploader_user_id,
        original_filename=original,
        storage_key=storage_key,
        file_size=len(content),
        mime_type=mime,
        kind=kind,
        message_id=message_id,
        quotation_id=quotation_id,
        version=version,
        version_group=version_group,
        category=category,
    )


def _guess_mime(ext: str) -> str:
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".txt": "text/plain",
        ".zip": "application/zip",
    }.get(ext, "application/octet-stream")


# ── realtime ──

@router.websocket("/ws/{opportunity_id}")
async def feed_ws(ws: WebSocket, opportunity_id: str, user_id: str = ""):
    """Live feed socket: pushes new messages/attachments + presence.

    Identity is passed as a ?user_id= query param (browsers can't easily set
    headers on WebSocket). Falls back to 匿名, mirroring the REST dependency.
    """
    repo = FeedUserRepository()
    try:
        user = repo.get(user_id) if user_id else None
        if not user:
            user = repo.get_or_create("匿名")
    finally:
        repo.close()
    await hub.connect(ws, opportunity_id, user["user_id"], user["name"])
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get("type") == "typing":
                await hub.broadcast(opportunity_id, {
                    "type": "typing",
                    "user_id": user["user_id"],
                    "name": user["name"],
                })
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws)
