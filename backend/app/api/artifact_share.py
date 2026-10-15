"""产出物分享 API — 网盘式链接分享（生成/列表/撤销 + 免登录下载）。

/authed：/api/portal/opp/{opp_id}/artifacts/*（商机访问权 + 敏感视角权限门禁）
/public：/api/share/{token}/*（token 即凭证；可过期/可撤销/可选提取码；下载计数留痕）
客户（报价）视角一期锁定——等效外发，二期开放时创建须过 ensure_outbound_approved。
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import ensure_opportunity_access, field_visible, get_current_user
from app.models.artifact_share import ArtifactShareToken, generate_share_token
from app.models.base import Opportunity_SessionLocal
from app.repository.feed_repo import FeedRepository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.quotation_repo import QuotationRepository
from app.services import artifact_share as share_svc
from app.services import quote_outbound_gate as outbound_gate
from app.services.storage_adapter import build_object_id, get_storage, now_iso

router = APIRouter(tags=["artifact-share"])


def _load_share_row(token: str, s=None):
    """按 token 读分享行（不校验提取码）；s=外部会话时不在内部关闭。"""
    own = s is None
    s = s or Opportunity_SessionLocal()
    try:
        row = s.execute(
            select(ArtifactShareToken).where(ArtifactShareToken.token == token)
        ).scalar_one_or_none()
        return row
    finally:
        if own:
            s.close()


def _check_alive(row) -> None:
    if row is None:
        raise HTTPException(status_code=404, detail="分享不存在或已失效")
    if row.revoked_at:
        raise HTTPException(status_code=410, detail="该分享已被撤销")
    if row.expires_at:
        try:
            from datetime import datetime
            if datetime.now() > datetime.fromisoformat(row.expires_at):
                raise HTTPException(status_code=410, detail="分享链接已过期")
        except ValueError:
            pass


def _gate_view(opportunity_id: str, source_type: str, source_id: str, view: str,
               user: Optional[dict] = None) -> None:
    """视角门禁：customer（报价）视角 = 报价数据出门——quote 来源须持有效外发许可
    （与导出/发送同一道闸，批的是内容指纹；持免审批权限者直通）；
    方案/成本来源的报价视角属内部传阅，不闸。"""
    if view == "customer" and source_type == "quote":
        repo = QuotationRepository()
        try:
            q = repo.get_by_id(str(source_id))
            if not q or q.opportunity_id != opportunity_id:
                raise HTTPException(status_code=404, detail="报价单不存在或不属于该商机")
            outbound_gate.ensure_outbound_approved(q, user)
        finally:
            repo.close()


def _cost_view_perm(view: str, user: dict) -> None:
    # 分享链接的接收方是免登录的，创建者的权限是唯一闸门——成本视角视同对内导出
    if view == "cost" and not field_visible(user, "field.quote.export_internal"):
        raise HTTPException(status_code=403, detail="成本视角含成本价，需要对内导出权限")


def _source_title(opportunity_id: str, source_type: str, source_id: str) -> tuple:
    """校验来源存在，返回 (title, customer_name)。"""
    opp_repo = OpportunityRepository()
    try:
        opp = opp_repo.get_opportunity(opportunity_id)
    finally:
        opp_repo.close()
    if not opp:
        raise HTTPException(status_code=404, detail="商机不存在")
    customer_name = opp.get("customer_name") or ""
    if source_type == "quote":
        repo = QuotationRepository()
        try:
            q = repo.get_by_id(str(source_id))
        finally:
            repo.close()
        if not q or q.opportunity_id != opportunity_id:
            raise HTTPException(status_code=404, detail="报价单不存在或不属于该商机")
        return q.quotation_name or f"报价单v{q.version}", customer_name
    return share_svc._load_configs(source_type, opportunity_id, str(source_id))[0], customer_name


class ShareCreateBody(BaseModel):
    source_type: str  # quote / cost / scheme
    source_id: str
    view: str = "internal"  # scheme / cost / internal（customer 一期锁定）
    template_id: Optional[int] = None
    expiry_days: int = 7
    extract_code: Optional[str] = None


@router.post("/api/portal/opp/{opportunity_id}/artifacts/share")
def create_artifact_share(opportunity_id: str, body: ShareCreateBody,
                          user: dict = Depends(get_current_user)):
    """生成分享：渲染落盘 + 归档附件桶 + 建 token。返回 token 信息与链接路径。"""
    ensure_opportunity_access(opportunity_id, user)
    if body.source_type not in share_svc.SOURCE_CATEGORY:
        raise HTTPException(status_code=422, detail="source_type 必须是 quote/cost/scheme")
    if body.view not in share_svc.VIEWS:
        raise HTTPException(status_code=422, detail="视角必须是 scheme/cost/customer")
    _gate_view(opportunity_id, body.source_type, body.source_id, body.view, user)
    _cost_view_perm(body.view, user)
    title, customer_name = _source_title(opportunity_id, body.source_type, body.source_id)

    content, filename = share_svc.build_share_file(
        opportunity_id, body.source_type, body.source_id, body.view, body.template_id)

    storage = get_storage()
    ext = Path(filename).suffix.lower() or ".xlsx"
    try:
        storage_key = storage.save_bytes(
            opportunity_id, build_object_id(filename), content, ext, customer_name,
            subfolder={"quote": "sent_quote", "cost": "requirement", "scheme": "technical"}.get(
                body.source_type, ""))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件保存失败: {e}")

    # 归档到商机附件桶（kind=export），分享出去的文件在档案里可追溯
    feed_repo = FeedRepository()
    attachment_id = ""
    try:
        att = feed_repo.add_attachment(
            opportunity_id=opportunity_id,
            uploader_user_id=user.get("user_id") or "",
            original_filename=filename,
            storage_key=storage_key,
            file_size=len(content),
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            kind="export",
            message_id=None,
            category=share_svc.SOURCE_CATEGORY.get(body.source_type),
            quotation_id=str(body.source_id) if body.source_type == "quote" else None,
        )
        attachment_id = att.get("attachment_id") or ""
    finally:
        feed_repo.close()

    row = ArtifactShareToken(
        token=generate_share_token(),
        opportunity_id=opportunity_id,
        source_type=body.source_type,
        source_id=str(body.source_id),
        title=title,
        view=body.view,
        template_id=body.template_id,
        filename=filename,
        storage_key=storage_key,
        attachment_id=attachment_id or None,
        extract_code=(body.extract_code or "").strip() or None,
        expires_at=share_svc.expiry_from_days(body.expiry_days),
        created_by=user.get("name") or "",
        created_at=now_iso(),
    )
    with Opportunity_SessionLocal() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
        result = row.to_dict()
    return {"share": result, "share_path": f"/api/share/{result['token']}"}


@router.get("/api/portal/opp/{opportunity_id}/artifacts/shares")
def list_artifact_shares(opportunity_id: str, source_type: str, source_id: str,
                         user: dict = Depends(get_current_user)):
    ensure_opportunity_access(opportunity_id, user)
    with Opportunity_SessionLocal() as s:
        rows = s.execute(
            select(ArtifactShareToken)
            .where(
                ArtifactShareToken.opportunity_id == opportunity_id,
                ArtifactShareToken.source_type == source_type,
                ArtifactShareToken.source_id == str(source_id),
            )
            .order_by(ArtifactShareToken.id.desc())
        ).scalars().all()
        return {"shares": [r.to_dict() for r in rows]}


@router.post("/api/portal/opp/{opportunity_id}/artifacts/shares/{share_id}/revoke")
def revoke_artifact_share(opportunity_id: str, share_id: int,
                          user: dict = Depends(get_current_user)):
    ensure_opportunity_access(opportunity_id, user)
    with Opportunity_SessionLocal() as s:
        row = s.execute(
            select(ArtifactShareToken).where(ArtifactShareToken.id == share_id)
        ).scalar_one_or_none()
        if not row or row.opportunity_id != opportunity_id:
            raise HTTPException(status_code=404, detail="分享不存在")
        is_admin = (user.get("role") or "") == "admin"
        if not is_admin and (row.created_by or "") != (user.get("name") or ""):
            raise HTTPException(status_code=403, detail="仅创建人或管理员可撤销")
        row.revoked_at = now_iso()
        s.commit()
        s.refresh(row)
        return {"share": row.to_dict()}


@router.get("/api/portal/opp/{opportunity_id}/artifacts/share/download")
def download_artifact_file(opportunity_id: str, source_type: str, source_id: str,
                           view: str, template_id: Optional[int] = None,
                           user: dict = Depends(get_current_user)):
    """登录态直接下载（不经链接）：同一渲染管线，实时生成。"""
    ensure_opportunity_access(opportunity_id, user)
    _gate_view(opportunity_id, source_type, source_id, view, user)
    _cost_view_perm(view, user)
    content, filename = share_svc.build_share_file(
        opportunity_id, source_type, str(source_id), view, template_id)
    return _xlsx_response(content, filename)


@router.get("/api/portal/opp/{opportunity_id}/artifacts/share/preview")
def preview_artifact_share(opportunity_id: str, source_type: str, source_id: str,
                           view: str, template_id: Optional[int] = None,
                           user: dict = Depends(get_current_user)):
    """分享弹窗预览：三节点同一模板管线，返回 Univer snapshot（前端只读渲染）。"""
    ensure_opportunity_access(opportunity_id, user)
    _gate_view(opportunity_id, source_type, source_id, view, user)
    _cost_view_perm(view, user)
    snapshot, _title, _filename = share_svc.render_entity_snapshot(
        opportunity_id, source_type, str(source_id), view, template_id)
    return {"kind": "univer", "workbook_snapshot": snapshot}


@router.get("/api/share/{token}")
def share_info(token: str):
    """免登录：分享落地页信息（文件名/有效期/是否需要提取码）。"""
    with Opportunity_SessionLocal() as s:
        row = _load_share_row(token, s)
        _check_alive(row)
        return {
            "title": row.title,
            "filename": row.filename,
            "view": row.view,
            "expires_at": row.expires_at or "",
            "needs_code": bool(row.extract_code),
            "created_by": row.created_by or "",
            "created_at": row.created_at or "",
        }


@router.get("/api/share/{token}/download")
def share_download(token: str, code: str = ""):
    """免登录下载：token 即凭证；提取码/过期/撤销校验 + 下载计数留痕。"""
    row_dict = share_svc.resolve_share(token, code)
    storage = get_storage()
    local = storage.resolve_local_path(row_dict.get("storage_key") or "")
    if local:
        return FileResponse(path=str(local), filename=row_dict.get("filename") or "file.xlsx",
                            media_type="application/octet-stream")
    url = storage.presigned_url(row_dict.get("storage_key") or "")
    if url:
        return RedirectResponse(url)
    raise HTTPException(status_code=404, detail="文件不可访问")


def _xlsx_response(content: bytes, filename: str):
    import tempfile
    fp = Path(tempfile.gettempdir()) / f"cpq_artifact_{build_object_id(filename)}.xlsx"
    fp.write_bytes(content)
    return FileResponse(path=str(fp), filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
