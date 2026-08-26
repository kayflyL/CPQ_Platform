import logging

logger = logging.getLogger(__name__)
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import FileResponse
from app.services.quote_service import QuoteService
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.feed_user_repo import FeedUserRepository
from app.api.deps import get_current_user, user_has_permission, require_opportunity_access, ensure_opportunity_access
import os
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel

# === File upload security constants ===
_ALLOWED_UPLOAD_EXTENSIONS = {
    '.xlsx', '.xls', '.csv', '.pdf', '.docx', '.doc',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.txt', '.zip',
}
_BLOCKED_OPEN_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.ps1', '.vbs', '.sh', '.com',
    '.scr', '.msi', '.jar', '.py', '.rb', '.php', '.js',
}
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
from urllib.parse import quote

router = APIRouter(
    prefix="/api/opportunities",
    tags=["opportunities"]
)


def _active_business_accounts() -> list[dict]:
    """启用中的业务角色账号，统一供创建/下拉/筛选使用。"""
    repo = FeedUserRepository()
    try:
        items = [
            {"user_id": u["user_id"], "name": u["name"]}
            for u in repo.list_all()
            if u.get("role") == "business" and u.get("is_active", True)
        ]
        items.sort(key=lambda x: x["name"])
        return items
    finally:
        repo.close()


class CreateOpportunityRequest(BaseModel):
    customer_name: str = ""
    sales_person: str = ""


class UpdateOpportunityRequest(BaseModel):
    customer_name: Optional[str] = None
    sales_person: Optional[str] = None
    fae: Optional[str] = None
    quotation_person: Optional[str] = None
    created_at: Optional[str] = None  # 允许管理员调整创建日期

    class Config:
        extra = "allow"  # Allow dynamic fields from field system


@router.post("/")
def create_empty_opportunity(req: CreateOpportunityRequest, user: dict = Depends(get_current_user)):
    """Create an empty opportunity manually."""
    repo = OpportunityRepository()
    try:
        customer_name = req.customer_name.strip()
        if not customer_name:
            raise HTTPException(status_code=400, detail="客户名称不能为空")

        view_all = user_has_permission(user, "page.opportunities_all")
        sales_person = req.sales_person.strip() or user.get("name") or ""
        owner_user_id = user.get("user_id")
        if not view_all:
            sales_person = user.get("name") or ""
        else:
            # 管理员可代业务建档：若销售名已是登录账号，归属该账号；否则归属当前管理员。
            target = next((u for u in _active_business_accounts() if u["name"] == sales_person), None)
            if target:
                owner_user_id = target["user_id"]
        opportunity_id = f"OPP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        repo.create_or_update_opportunity(opportunity_id, {
            "customer_name": customer_name,
            "sales_person": sales_person,
            "owner_user_id": owner_user_id,
        })

        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "message": "商机创建成功"
        }
    finally:
        repo.close()


@router.get("/list")
def list_opportunities(page: int = 1, page_size: int = 50, include_deleted: bool = False, search: str = None, status: str = None, platform: str = None, chassis: str = None, result: str = None, industry: str = None, order_type: str = None, sales_person: str = None, sort_by: str = "updated_at", sort_order: str = "desc", user: dict = Depends(get_current_user)):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        view_all = user_has_permission(user, "page.opportunities_all")
        if not view_all:
            raise HTTPException(status_code=403, detail="无权查看商机线索")
        items, total = repo.list_opportunities(
            include_deleted, page, page_size,
            search=search, status=status, platform=platform, chassis=chassis,
            result=result, industry=industry, order_type=order_type,
            sales_person=sales_person,
            owner_user_id=None,
            owner_sales_person=None,
            has_committed_requirement=True,
            sort_by=sort_by, sort_order=sort_order,
        )
        return {"items": items, "total": total}
    finally:
        repo.close()


@router.get("/sales-options")
def list_sales_options(user: dict = Depends(get_current_user)):
    """业务账户选项（仅全量视图权限可读，业务个人页不会调用）。"""
    if not user_has_permission(user, "page.opportunities_all"):
        return {"items": []}
    return {"items": [u["name"] for u in _active_business_accounts()]}


@router.get("/business-options")
def list_business_options(user: dict = Depends(get_current_user)):
    """业务账户下拉：从 feed_users 中取启用中的业务角色账号。"""
    if not user_has_permission(user, "page.opportunities_all"):
        return {"items": []}
    return {"items": _active_business_accounts()}


@router.put("/{opportunity_id}")
def update_opportunity(opportunity_id: str, req: UpdateOpportunityRequest,
                       user: dict = Depends(require_opportunity_access)):
    """Update opportunity basic info (supports dynamic fields)

    When customer_name changes, also rename storage folder and update
    storage_key in feed_attachments.
    """
    repo = OpportunityRepository()
    try:
        updates = req.dict(exclude_unset=True)

        # 这些字段已迁移到需求单 slots，商机基本信息更新不再落库到 opportunities.extra_fields。
        for key in ("platform_type", "chassis_form", "purchase_qty", "warranty_years"):
            updates.pop(key, None)

        # 商机级角色字段锁定：对应角色登录时该字段强制为当前登录人，不可修改。
        role = user.get("role")
        current_name = user.get("name") or ""
        if role == "business":
            updates["sales_person"] = current_name
        elif role == "te":
            updates["fae"] = current_name
        elif role == "quote":
            updates["quotation_person"] = current_name

        if not user_has_permission(user, "page.opportunities_all"):
            updates.pop("owner_user_id", None)
            updates.pop("created_at", None)
        elif "sales_person" in updates:
            target = next(
                (u for u in _active_business_accounts() if u["name"] == str(updates.get("sales_person") or "").strip()),
                None,
            )
            if target:
                updates["owner_user_id"] = target["user_id"]

        if not updates:
            return {"status": "success", "message": "No fields to update"}

        # 如果客户名变更，需要重命名存储文件夹
        if "customer_name" in updates:
            # 获取旧的商机信息
            old_opp = repo.get_opportunity(opportunity_id)
            old_customer = old_opp.get("customer_name", "") if old_opp else ""

            new_customer = updates["customer_name"] or ""

            # 如果客户名确实变更了
            if old_customer != new_customer:
                from app.services.storage_adapter import get_storage
                from app.repository.feed_repo import FeedRepository

                storage = get_storage()
                success, prefixes = storage.rename_opportunity_folder(
                    opportunity_id, old_customer, new_customer
                )

                if success and prefixes.get("old_prefix") and prefixes.get("new_prefix"):
                    # 更新 feed_attachments 中的 storage_key
                    feed_repo = FeedRepository()
                    try:
                        feed_repo.update_storage_key_prefix(
                            opportunity_id,
                            prefixes["old_prefix"],
                            prefixes["new_prefix"]
                        )
                    finally:
                        feed_repo.close()

        success = repo.update_meta(opportunity_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")

        return {"status": "success", "message": "Project updated"}
    finally:
        repo.close()


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str, _user: dict = Depends(require_opportunity_access)):
    service = QuoteService()
    try:
        result = service.get_opportunity_details(opportunity_id)
        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result
    finally:
        service.close()


@router.post("/save")
def save_opportunity(data: dict, user: dict = Depends(get_current_user)):
    """Save opportunity (file archiving goes through FeedAttachment / StorageAdapter)."""
    service = QuoteService()
    try:
        opportunity_info = dict(data.get("opportunity_info") or {})
        configs = data.get("configs", {})
        config_quantities = data.get("config_quantities", {})
        opportunity_id = str(opportunity_info.get("opportunity_id") or "").strip()
        view_all = user_has_permission(user, "page.opportunities_all")
        role = user.get("role")
        current_name = user.get("name") or ""
        if role == "business":
            opportunity_info["sales_person"] = current_name
        elif role == "te":
            opportunity_info["fae"] = current_name
        elif role == "quote":
            opportunity_info["quotation_person"] = current_name
        if opportunity_id:
            ensure_opportunity_access(opportunity_id, user)
            opportunity_info.pop("owner_user_id", None)
        else:
            opportunity_info["owner_user_id"] = user.get("user_id")
            if not view_all:
                opportunity_info["sales_person"] = user.get("name") or opportunity_info.get("sales_person") or ""

        result = service.save_opportunity(opportunity_info, configs, config_quantities)
        return result
    except Exception as e:
        import traceback
        print(f"[ERROR save_opportunity] UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        service.close()


@router.get("/field-history/{field_key}")
def get_field_history(field_key: str, q: str = None, limit: int = 20,
                      user: dict = Depends(get_current_user)):
    """Get historical values for a field across all opportunities (for autocomplete)."""
    import json
    from collections import Counter
    from sqlalchemy import text
    
    repo = OpportunityRepository()
    try:
        # Validate field exists in business_fields
        check_sql = text("SELECT key FROM rules.business_fields WHERE key = :key")
        exists = repo.session.execute(check_sql, {"key": field_key}).fetchone()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Unknown field: {field_key}")
        
        # Core columns that are actual DB columns
        core_columns = {
            "customer_name", "sales_person", "fae",
            "quotation_person",
            "industry", "order_type",
        }
        view_all = user_has_permission(user, "page.opportunities_all")
        owner_user_id = None if view_all else (user.get("user_id") or None)
        owner_sales_person = None if view_all else (user.get("name") or None)
        scope_sql = ""
        scope_params = {}
        if owner_user_id:
            scope_sql = " AND (owner_user_id = :owner_user_id OR (owner_user_id IS NULL AND sales_person = :owner_sales_person))"
            scope_params = {"owner_user_id": owner_user_id, "owner_sales_person": owner_sales_person}
        elif owner_sales_person:
            scope_sql = " AND sales_person = :owner_sales_person"
            scope_params = {"owner_sales_person": owner_sales_person}
        
        values = []
        
        if field_key in core_columns:
            # Query from core column
            sql = text(f"SELECT {field_key} FROM opportunities.opportunities WHERE status != 'deleted' AND {field_key} IS NOT NULL AND {field_key} != ''{scope_sql}")
            result = repo.session.execute(sql, scope_params).fetchall()
            values = [row[0] for row in result if row[0]]
        else:
            # Query from extra_fields JSON
            sql = text(f"SELECT extra_fields FROM opportunities.opportunities WHERE status != 'deleted' AND extra_fields IS NOT NULL{scope_sql}")
            result = repo.session.execute(sql, scope_params).fetchall()
            for row in result:
                try:
                    extra = json.loads(row[0])
                    if field_key in extra and extra[field_key]:
                        values.append(extra[field_key])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Count frequency
        counter = Counter(values)
        
        # Filter by keyword if provided
        if q:
            q_lower = q.lower()
            counter = Counter({k: v for k, v in counter.items() if q_lower in str(k).lower()})
        
        # Sort by frequency (descending), then alphabetically
        sorted_values = sorted(counter.items(), key=lambda x: (-x[1], str(x[0])))
        
        # Return top N values
        result_values = [str(v) for v, count in sorted_values[:limit]]
        
        return {"values": result_values, "total": len(counter)}
    finally:
        repo.close()


@router.post("/{opportunity_id}/trash")
def move_to_trash(opportunity_id: str, _user: dict = Depends(require_opportunity_access)):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.move_to_trash(opportunity_id)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.post("/{opportunity_id}/restore")
def restore_opportunity(opportunity_id: str, _user: dict = Depends(require_opportunity_access)):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.restore_opportunity(opportunity_id)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.delete("/{opportunity_id}")
def permanent_delete(opportunity_id: str, _user: dict = Depends(require_opportunity_access)):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.permanent_delete(opportunity_id)
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()

    # DB record gone — best-effort purge of the on-disk folder. Match by
    # opportunity_id so a name-drifted folder (e.g. 未命名_OPP-…) is still found.
    try:
        from app.services.storage_adapter import get_storage
        get_storage().delete_opportunity_folder(opportunity_id)
    except Exception:
        logger.exception("On-disk folder cleanup failed")

    return {"status": "success"}


@router.put("/{opportunity_id}/meta")
def update_opportunity_meta(opportunity_id: str, updates: dict,
                            user: dict = Depends(require_opportunity_access)):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        if not user_has_permission(user, "page.opportunities_all"):
            updates.pop("owner_user_id", None)
            updates.pop("created_at", None)
        repo.update_meta(opportunity_id, updates)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


# ── Batch Operations ──

class BatchOpportunityRequest(BaseModel):
    opportunity_ids: List[str]


@router.post("/batch-trash")
def batch_move_to_trash(req: BatchOpportunityRequest, user: dict = Depends(get_current_user)):
    """批量移至回收站"""
    repo = OpportunityRepository()
    results = {"success": [], "failed": []}
    try:
        for pid in req.opportunity_ids:
            try:
                ensure_opportunity_access(pid, user)
                repo.move_to_trash(pid)
                results["success"].append(pid)
            except Exception as e:
                results["failed"].append({"id": pid, "error": str(e)})
        return results
    finally:
        repo.close()


@router.post("/batch-restore")
def batch_restore(req: BatchOpportunityRequest, user: dict = Depends(get_current_user)):
    """批量从回收站恢复"""
    repo = OpportunityRepository()
    results = {"success": [], "failed": []}
    try:
        for pid in req.opportunity_ids:
            try:
                ensure_opportunity_access(pid, user)
                repo.restore_opportunity(pid)
                results["success"].append(pid)
            except Exception as e:
                results["failed"].append({"id": pid, "error": str(e)})
        return results
    finally:
        repo.close()


@router.post("/batch-permanent-delete")
def batch_permanent_delete(req: BatchOpportunityRequest, user: dict = Depends(get_current_user)):
    """批量永久删除"""
    from app.services.storage_adapter import get_storage
    repo = OpportunityRepository()
    results = {"success": [], "failed": []}
    try:
        storage = get_storage()
        for pid in req.opportunity_ids:
            try:
                ensure_opportunity_access(pid, user)
                repo.permanent_delete(pid)
                results["success"].append(pid)
                # Best-effort: physically remove the on-disk folder too.
                try:
                    storage.delete_opportunity_folder(pid)
                except Exception:
                    logger.exception("On-disk folder cleanup failed for %s", pid)
            except Exception as e:
                results["failed"].append({"id": pid, "error": str(e)})
        return results
    finally:
        repo.close()
