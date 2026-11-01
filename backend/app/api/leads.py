"""线索池 API（登录态）—— 公开线索的人工筛选与转化分配。

权限：page.leads 查看；action.lead.manage 确认/转化/驳回（专人）。
转化 = 原子抢占（converting 瞬态防并发）→ 建商机 → extra_fields 溯源 →
需求草稿（登记表 slots 原样，业务零重填）→ 附件转钉 requirement_version → 企微通知（尽力而为）。
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import require_perms
from app.models.base import Opportunity_SessionLocal
from app.models.feed_attachment import FeedAttachment
from app.repository.flow_repo import FlowRepository
from app.repository.lead_repo import LeadRepository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.utils.file_storage import FileStorage

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _reject_reason_keys() -> set:
    repo = SystemConfigRepository()
    try:
        items = repo.get_value("lead.reject_reasons", []) or []
        return {r.get("key") for r in items if isinstance(r, dict) and r.get("enabled", True) and r.get("key")}
    finally:
        repo.close()


@router.get("")
def list_leads(status: str = "", search: str = "", page: int = 1, page_size: int = 20,
               user: dict = Depends(require_perms("page.leads"))):
    repo = LeadRepository()
    try:
        return repo.list_leads(status=status, search=search, page=max(page, 1), page_size=min(page_size, 100))
    finally:
        repo.close()


@router.get("/business-options")
def business_options(user: dict = Depends(require_perms("page.leads"))):
    repo = LeadRepository()
    try:
        return {"options": repo.business_options()}
    finally:
        repo.close()


@router.get("/{lead_id}")
def get_lead(lead_id: str, user: dict = Depends(require_perms("page.leads"))):
    repo = LeadRepository()
    try:
        lead = repo.get(lead_id)
        if not lead:
            raise HTTPException(404, "线索不存在")
        return lead
    finally:
        repo.close()


@router.get("/{lead_id}/attachments/{index}")
def download_lead_attachment(lead_id: str, index: int, user: dict = Depends(require_perms("page.leads"))):
    repo = LeadRepository()
    try:
        lead = repo.get(lead_id)
    finally:
        repo.close()
    if not lead:
        raise HTTPException(404, "线索不存在")
    items = lead.get("attachments") or []
    if index < 0 or index >= len(items):
        raise HTTPException(404, "附件不存在")
    storage = FileStorage()
    rel = items[index].get("storage_key") or ""
    target = storage.base_path.joinpath(*rel.split("/"))
    try:
        resolved = target.resolve()
        resolved.relative_to(storage.base_path.resolve())
    except (ValueError, OSError):
        raise HTTPException(400, "非法路径")
    if not resolved.is_file():
        raise HTTPException(404, "附件文件已不存在")
    return FileResponse(str(resolved), filename=items[index].get("name") or resolved.name)


class ConfirmRequest(BaseModel):
    pass


@router.post("/{lead_id}/confirm")
def confirm_lead(lead_id: str, user: dict = Depends(require_perms("action.lead.manage"))):
    repo = LeadRepository()
    try:
        if not repo.get(lead_id):
            raise HTTPException(404, "线索不存在")
        final = repo.mark_confirmed(lead_id)
        if final is None:
            raise HTTPException(409, "线索当前状态不可确认")
        return {"ok": True, "status": final}
    finally:
        repo.close()


class RejectRequest(BaseModel):
    reason: str
    note: str = ""


@router.post("/{lead_id}/delete")
def delete_lead(lead_id: str, user: dict = Depends(require_perms("action.lead.manage"))):
    """软删除（回收站语义）：未转化线索可删；已转化背着商机溯源，不可删。"""
    repo = LeadRepository()
    try:
        lead = repo.get(lead_id)
        if not lead:
            raise HTTPException(404, "线索不存在")
        if lead["status"] in ("assigned", "converting"):
            raise HTTPException(409, "已转化的线索不可删除（商机溯源依赖它）")
        if not repo.mark_deleted(lead_id):
            raise HTTPException(409, "线索当前状态不可删除")
        return {"ok": True}
    finally:
        repo.close()


@router.post("/{lead_id}/restore")
def restore_lead(lead_id: str, user: dict = Depends(require_perms("action.lead.manage"))):
    """从回收站恢复：回到待处理（new），重新进入专人筛选。"""
    repo = LeadRepository()
    try:
        if not repo.restore_deleted(lead_id):
            raise HTTPException(409, "仅回收站中的线索可恢复")
        return {"ok": True, "status": "new"}
    finally:
        repo.close()


@router.post("/{lead_id}/reject")
def reject_lead(lead_id: str, body: RejectRequest, user: dict = Depends(require_perms("action.lead.manage"))):
    enabled = _reject_reason_keys()
    if body.reason not in enabled:
        raise HTTPException(422, "驳回原因不在字典内")
    repo = LeadRepository()
    try:
        if not repo.get(lead_id):
            raise HTTPException(404, "线索不存在")
        if not repo.mark_rejected(lead_id, body.reason, body.note):
            raise HTTPException(409, "线索当前状态不可驳回")
        return {"ok": True}
    finally:
        repo.close()


class ConvertRequest(BaseModel):
    assignee_user_id: str


def _pin_lead_attachments(lead: dict, opportunity_id: str, requirement_version: int, operator_user_id: str) -> None:
    """线索附件转钉到需求草稿版本（FeedAttachment，category=requirement；文件留在原位）。"""
    session = Opportunity_SessionLocal()
    try:
        for att in lead.get("attachments") or []:
            session.add(FeedAttachment(
                attachment_id=uuid.uuid4().hex,
                opportunity_id=opportunity_id,
                uploader_user_id=operator_user_id,
                original_filename=att.get("name") or "attachment",
                storage_key=att.get("storage_key") or "",
                file_size=int(att.get("size") or 0),
                mime_type=None,
                kind="upload",
                category="requirement",
                requirement_version=requirement_version,
                created_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
            ))
        session.commit()
    finally:
        session.close()


@router.post("/{lead_id}/convert")
def convert_lead(lead_id: str, body: ConvertRequest, user: dict = Depends(require_perms("action.lead.manage"))):
    repo = LeadRepository()
    try:
        lead = repo.get(lead_id)
        if not lead:
            raise HTTPException(404, "线索不存在")
        if lead["status"] not in ("new", "confirmed"):
            raise HTTPException(409, "线索当前状态不可转化")
        target = next((o for o in repo.business_options() if o["user_id"] == body.assignee_user_id), None)
        if not target:
            raise HTTPException(409, "归属业务不存在或未启用")
        if not repo.try_mark_converting(lead_id):
            raise HTTPException(409, "线索已被他人处理")

        try:
            opportunity_id = f"OPP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            customer_name = lead["company"] or f"{lead['contact_name']} - 官网线索" or "官网线索"
            OpportunityRepository().create_or_update_opportunity(opportunity_id, {
                "customer_name": customer_name,
                "sales_person": target["name"],
                "owner_user_id": target["user_id"],
            })
            OpportunityRepository().update_meta(opportunity_id, {
                "lead_id": lead_id,
                "lead_source": lead["source"],
            })
            draft = FlowRepository().create_or_update_requirement_draft(
                opportunity_id,
                slots=lead.get("config_slots") or {},
                requirement_text=lead.get("requirement_text") or "",
                created_by=user.get("name") or "",
            )
            _pin_lead_attachments(lead, opportunity_id, draft["version"], user.get("user_id") or "")
            repo.finalize_converted(lead_id, opportunity_id, target["user_id"])
        except Exception:
            repo.restore_from_converting(lead_id)
            raise HTTPException(500, "转化失败，线索已回滚，请重试")

        # 企微通知归属业务（尽力而为，不阻塞）
        try:
            from app.services.wecom_client import enqueue_text
            enqueue_text(target["name"], f"新线索已转商机 {opportunity_id}：{customer_name}（{lead.get('contact_name') or '未留姓名'}），请到商机详情确认需求草稿")
        except Exception:
            pass

        return {"ok": True, "opportunity_id": opportunity_id, "requirement_version": draft["version"]}
    finally:
        repo.close()
