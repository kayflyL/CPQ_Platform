"""Quotation API endpoints."""
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.api.deps import get_current_user, field_visible, require_perms, ensure_opportunity_access, require_quotation_access, ensure_quotation_access, user_has_permission
from app.utils.price_mask import mask_price_fields
from app.repository.quotation_repo import QuotationRepository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.feed_repo import FeedRepository
from app.repository.flow_card_repo import FlowCardRepository

router = APIRouter(prefix="/api/quotations", tags=["quotations"])


class QuotationCreate(BaseModel):
    opportunity_id: str
    file_path: Optional[str] = None
    quotation_date: Optional[str] = None
    quotation_name: Optional[str] = None


class QuotationUpdate(BaseModel):
    model_config = {"extra": "allow"}  # 支持动态字段

    l6_price: Optional[float] = None
    total_qty: Optional[int] = None
    config_count: Optional[int] = None
    config_quantities: Optional[dict] = None
    quotation_date: Optional[str] = None
    quotation_name: Optional[str] = None
    expected_updated_at: Optional[str] = None  # 乐观锁基线，不落库


@router.get("")
def list_quotations(opportunity_id: Optional[str] = None, include_deleted: bool = False,
                    user: dict = Depends(get_current_user)):
    """List all quotations, optionally filtered by opportunity_id."""
    repo = QuotationRepository()
    try:
        if opportunity_id:
            ensure_opportunity_access(opportunity_id, user)
        elif not user_has_permission(user, "page.opportunities_all"):
            raise HTTPException(status_code=403, detail="缺少商机范围")
        from app.models.quotation import Quotation
        from app.models.base import Opportunity_SessionLocal
        session = Opportunity_SessionLocal()
        try:
            query = session.query(Quotation)
            if opportunity_id:
                query = query.filter(Quotation.opportunity_id == opportunity_id)
            if not include_deleted:
                query = query.filter(Quotation.status == "active")
            quotations = query.order_by(Quotation.created_at.desc()).all()
        finally:
            session.close()
        # 列表保持精简：剥离 cost_snapshot（抽屉按需走 GET /{id} 取）
        show_price = field_visible(user, "field.opportunity.quote_price")
        items_list = []
        for q in quotations:
            d = q.to_dict()
            d.pop("cost_snapshot", None)
            if not show_price:
                d = mask_price_fields(d)
            items_list.append(d)
        return {"quotations": items_list}
    finally:
        repo.close()


@router.get("/{quotation_id}")
def get_quotation(quotation_id: str, reparse: bool = False,
                  user: dict = Depends(require_quotation_access)):
    """Get a quotation by ID with its items.

    Args:
        reparse: If True, re-parse source Excel to rebuild per-config L6 data.
                 Defaults to False (use stored data) for performance.
    """
    repo = QuotationRepository()
    opp_repo = OpportunityRepository()
    try:
        quotation = repo.get_by_id(quotation_id)
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        
        result = quotation.to_dict()
        
        # Include opportunity info (customer_name)
        opportunity = opp_repo.get_opportunity(quotation.opportunity_id)
        if opportunity:
            result["customer_name"] = opportunity.get("customer_name", "") or ""
        
        # Add date field (from quotation_date or created_at)
        result["date"] = result.get("quotation_date", "") or (result.get("created_at", "")[:10] if result.get("created_at") else "")
        
        # Add description field (from opportunity l6_spec or model_name)
        result["description"] = opportunity.get("l6_spec", "") or opportunity.get("model_name", "") if opportunity else ""
        
        # Include items in response for frontend workspace loading
        items = repo.get_items(quotation_id)
        result["items"] = [item.to_dict() for item in items]

        per_cfg_l6 = {}

        # Try stored per-config L6 data first (fast path, no Excel re-parsing)
        stored = result.get("per_cfg_l6")
        if isinstance(stored, str):
            import json as _json
            try:
                stored = _json.loads(stored)
            except Exception:
                stored = {}
        if stored and not reparse:
            per_cfg_l6 = stored
        elif reparse:
            # Only re-parse Excel when explicitly requested
            from app.services.quote_service import QuoteService
            try:
                svc = QuoteService()
                try:
                    file_content = None
                    file_path = quotation.file_path
                    if file_path:
                        import os
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                file_content = f.read()
                    if file_content is not None:
                        parsed = svc.process_upload(file_content, os.path.basename(file_path))
                        if parsed.get("status") != "error":
                            for cfg_name, cfg_data in parsed.get("configs", {}).items():
                                per_cfg_l6[cfg_name] = {}
                except Exception as e:
                    logger.warning("per-config L6 rebuild failed: %s", e)
                finally:
                    svc.close()
            except Exception as e:
                logger.warning("QuoteService init failed: %s", e)

        result["per_cfg_l6"] = per_cfg_l6

        # 字段级价格掩码（报价工作台价格权限）：不可见 → 价格字段置空 + 快照整体置空
        if not field_visible(user, "field.quote.price"):
            result = mask_price_fields(result)
            result["cost_snapshot"] = None
            result["strategy_snapshot"] = None

        return result
    finally:
        repo.close()
        opp_repo.close()


@router.post("")
def create_quotation(req: QuotationCreate, user: dict = Depends(get_current_user)):
    """Create a new quotation."""
    ensure_opportunity_access(req.opportunity_id, user)
    # Verify opportunity exists
    opp_repo = OpportunityRepository()
    try:
        opportunity = opp_repo.get_opportunity(req.opportunity_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity not found")
    finally:
        opp_repo.close()
    
    quo_repo = QuotationRepository()
    try:
        quotation = quo_repo.create(
            req.opportunity_id,
            req.file_path,
            quotation_date=req.quotation_date,
            quotation_name=req.quotation_name
        )
        return {"quotation_id": quotation.quotation_id, "quotation": quotation.to_dict()}
    finally:
        quo_repo.close()


@router.put("/{quotation_id}")
def update_quotation(quotation_id: str, req: QuotationUpdate,
                     _user: dict = Depends(require_quotation_access)):
    """Update a quotation."""
    repo = QuotationRepository()
    try:
        update_data = req.dict(exclude_unset=True)
        baseline = (update_data.pop("expected_updated_at", None) or "").strip()
        if baseline:
            current = repo.get_raw_by_id(quotation_id)
            if not current:
                raise HTTPException(status_code=404, detail="Quotation not found")
            if (current.updated_at or "") != baseline:
                raise HTTPException(status_code=409, detail="报价单内容已被他人修改，请刷新后重试")
        quotation = repo.update(quotation_id, **update_data)
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"quotation": quotation.to_dict()}
    finally:
        repo.close()


@router.delete("/{quotation_id}")
def delete_quotation(quotation_id: str, _user: dict = Depends(require_quotation_access)):
    """Permanently delete a quotation (with items, archive attachments & flow-card refs)."""
    repo = QuotationRepository()
    feed_repo = FeedRepository()
    flow_card_repo = FlowCardRepository()
    try:
        opp_id = repo.permanent_delete(quotation_id)
        if not opp_id:
            raise HTTPException(status_code=404, detail="Quotation not found")
        _cleanup_quotation_refs(opp_id, quotation_id, feed_repo, flow_card_repo)
        return {"message": "Quotation deleted"}
    finally:
        repo.close()
        feed_repo.close()
        flow_card_repo.close()


def _cleanup_quotation_refs(opp_id: str, quotation_id: str, feed_repo, flow_card_repo) -> Optional[dict]:
    """清理报价单关联：归档附件与流程卡 quote 实体引用（失败不阻断主删除）。
    返回附件删除信息（opportunity_id + attachment_ids），供 WebSocket 广播使用。"""
    att_info = None
    try:
        del_info = feed_repo.soft_delete_attachments_by_quotation(quotation_id)
        if del_info:
            att_info = {"opportunity_id": del_info[0], "attachment_ids": del_info[1:]}
    except Exception:
        pass
    try:
        card = flow_card_repo.get_card_for_entity(opp_id, "quote", quotation_id)
        if card:
            flow_card_repo.unlink_entity(card["id"], "quote", quotation_id, opportunity_id=opp_id)
            flow_card_repo.delete_card_if_empty(card["id"])
    except Exception:
        pass
    return att_info


@router.post("/{quotation_id}/set-primary")
def set_primary_quotation(quotation_id: str, _user: dict = Depends(require_quotation_access)):
    """Set a quotation as primary (is_primary=True) and clear others for the same opportunity."""
    repo = QuotationRepository()
    try:
        success = repo.set_primary(quotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"message": "Quotation set as primary"}
    finally:
        repo.close()


class CostSnapshotRequest(BaseModel):
    cost_snapshot: dict


@router.post("/{quotation_id}/export")
def export_quotation(quotation_id: str, req: CostSnapshotRequest,
                     admin: dict = Depends(require_perms("field.quote.price")),
                     _user: dict = Depends(require_quotation_access)):
    """Freeze a draft quotation into an exported one: stamp exported_at and persist the
    cost snapshot captured client-side. Idempotent — re-exporting just refreshes the snapshot."""
    repo = QuotationRepository()
    try:
        quotation = repo.get_by_id(quotation_id)
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        updated = repo.mark_exported(quotation_id, req.cost_snapshot, datetime.now().isoformat())
        return {"quotation": updated.to_dict()}
    finally:
        repo.close()


@router.post("/{quotation_id}/unfreeze")
def unfreeze_quotation(quotation_id: str,
                       admin: dict = Depends(require_perms("action.quote.unfreeze")),
                       _user: dict = Depends(require_quotation_access)):
    """解冻已导出报价单（需 action.quote.unfreeze 权限）：清 exported_at 回到草稿态，
    重新进工作台编辑。已发送（报价单已出）的单不允许解冻，需先退回审批节点。"""
    repo = QuotationRepository()
    try:
        quotation = repo.get_by_id(quotation_id)
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        if not quotation.exported_at:
            raise HTTPException(status_code=400, detail="该报价单未导出，无需解冻")
        if quotation.submitted_at:
            raise HTTPException(status_code=409, detail="该报价单已发送，请先退回审批节点后再解冻")
        updated = repo.unfreeze(quotation_id)
        return {"quotation": updated.to_dict()}
    finally:
        repo.close()


@router.post("/{quotation_id}/reparse")
def reparse_quotation(quotation_id: str, _user: dict = Depends(require_quotation_access)):
    """Clone an exported quotation into a NEW (unexported) quotation.

    Re-parsing the archived export Excel is unreliable (the export has a different layout
    than the upload template the parser expects). The source quotation's DB items are the
    authoritative structured data, so we clone those + config-level fields instead. The
    original exported row stays frozen. Each clone is an independent quotation — an
    opportunity may have multiple unexported quotations side by side.
    """
    repo = QuotationRepository()
    try:
        source = repo.get_by_id(quotation_id)
        if not source:
            raise HTTPException(status_code=404, detail="Quotation not found")
        if not source.exported_at:
            raise HTTPException(status_code=400, detail="该报价单为草稿，请直接编辑")

        new_quotation = repo.create(source.opportunity_id)
        repo.copy_quotation_state(quotation_id, new_quotation.quotation_id)
        return {"quotation_id": new_quotation.quotation_id}
    finally:
        repo.close()


@router.post("/{quotation_id}/restore")
def restore_quotation(quotation_id: str, _user: dict = Depends(require_quotation_access)):
    """Restore a soft-deleted quotation."""
    repo = QuotationRepository()
    try:
        success = repo.restore(quotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"message": "Quotation restored"}
    finally:
        repo.close()


@router.get("/{quotation_id}/items")
def get_quotation_items(quotation_id: str, user: dict = Depends(require_quotation_access)):
    """Get all items for a quotation."""
    repo = QuotationRepository()
    try:
        items = repo.get_items(quotation_id)
        rows = [item.to_dict() for item in items]
        if not field_visible(user, "field.quote.price"):
            rows = mask_price_fields(rows)
        return {"items": rows}
    finally:
        repo.close()


@router.post("/{quotation_id}/items")
def save_quotation_items(quotation_id: str, data: dict,
                         _user: dict = Depends(require_quotation_access)):
    """Save configuration items + config_quantities + config_descriptions + config_server_models + config_warranty_info for a quotation."""
    repo = QuotationRepository()
    try:
        # Support both new payload format (dict with items/config_quantities) and legacy (list of items)
        if isinstance(data, list):
            items = data
            config_quantities = None
            config_descriptions = None
            config_server_models = None
            config_warranty_info = None
        else:
            items = data.get("items", [])
            config_quantities = data.get("config_quantities")
            config_descriptions = data.get("config_descriptions")
            config_server_models = data.get("config_server_models")
            config_warranty_info = data.get("config_warranty_info")
            config_l6_picks = data.get("config_l6_picks")
            config_relation = data.get("config_relation")
            primary_config = data.get("primary_config")
            top_total_qty = data.get("total_qty")

        # 先更新 config-level 字段（config_warranty_info / config_l6_picks 等），再 save_items。
        update_kwargs = {}
        if config_quantities:
            update_kwargs["config_quantities"] = config_quantities
        if config_descriptions:
            update_kwargs["config_descriptions"] = config_descriptions
        if config_server_models:
            update_kwargs["config_server_models"] = config_server_models
        if config_warranty_info:
            update_kwargs["config_warranty_info"] = config_warranty_info
        if config_l6_picks:
            update_kwargs["config_l6_picks"] = config_l6_picks
        if config_relation:
            update_kwargs["config_relation"] = config_relation
        if primary_config is not None:
            update_kwargs["primary_config"] = primary_config
        # 设备数量：方案备选取需求台数（total_qty 由前端算好透传），组合拆分取各配置台数之和
        if config_quantities:
            if (config_relation or "compose") == "alternative":
                total_qty = int(top_total_qty or 0) or sum(int(q) for q in config_quantities.values() if q)
            else:
                total_qty = sum(int(q) for q in config_quantities.values() if q)
            update_kwargs["total_qty"] = total_qty
        if update_kwargs:
            repo.update(quotation_id, **update_kwargs)

        count = repo.save_items(quotation_id, items)

        # total_price / profit_margin 由前端工作台算好直接存（单一计算源）。
        # calculate_totals 不再算这俩（只 config_count），消除前后端两套口径漂移。
        if isinstance(data, dict):
            price_fields = {}
            if data.get("total_price") is not None:
                price_fields["total_price"] = float(data["total_price"])
            if data.get("profit_margin") is not None:
                price_fields["profit_margin"] = float(data["profit_margin"])
            if data.get("l6_price") is not None:
                price_fields["l6_price"] = float(data["l6_price"])
            if price_fields:
                repo.update(quotation_id, **price_fields)

        return {"saved": count}
    finally:
        repo.close()


# ── Batch Operations ──

class BatchQuotationRequest(BaseModel):
    quotation_ids: List[str]


@router.post("/batch-delete")
def batch_delete_quotations(req: BatchQuotationRequest, user: dict = Depends(get_current_user)):
    """批量永久删除报价单（含明细、归档附件与流程卡引用）。"""
    repo = QuotationRepository()
    feed_repo = FeedRepository()
    flow_card_repo = FlowCardRepository()
    results = {"success": [], "failed": []}
    try:
        for qid in req.quotation_ids:
            try:
                ensure_quotation_access(qid, user)
                opp_id = repo.permanent_delete(qid)
                if opp_id:
                    _cleanup_quotation_refs(opp_id, qid, feed_repo, flow_card_repo)
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})
        return results
    finally:
        repo.close()
        feed_repo.close()
        flow_card_repo.close()


@router.post("/batch-restore")
def batch_restore_quotations(req: BatchQuotationRequest, user: dict = Depends(get_current_user)):
    """批量恢复报价单"""
    repo = QuotationRepository()
    results = {"success": [], "failed": []}
    try:
        for qid in req.quotation_ids:
            try:
                ensure_quotation_access(qid, user)
                repo.restore(qid)
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})
        return results
    finally:
        repo.close()


@router.post("/batch-permanent-delete")
async def batch_permanent_delete_quotations(req: BatchQuotationRequest,
                                             user: dict = Depends(get_current_user)):
    """批量永久删除报价单（含明细、归档附件与流程卡引用）"""
    repo = QuotationRepository()
    feed_repo = FeedRepository()
    flow_card_repo = FlowCardRepository()
    results = {"success": [], "failed": []}
    # 收集需要广播的删除事件
    attachment_deletions: List[dict] = []
    try:
        for qid in req.quotation_ids:
            try:
                ensure_quotation_access(qid, user)
                opp_id = repo.permanent_delete(qid)
                if not opp_id:
                    raise HTTPException(status_code=404, detail="报价单不存在")
                att_info = _cleanup_quotation_refs(opp_id, qid, feed_repo, flow_card_repo)
                if att_info:
                    attachment_deletions.append(att_info)
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})

        # 广播附件删除事件（让已连接的客户端同步更新）
        from app.services.feed_hub import hub
        for item in attachment_deletions:
            for att_id in item.get("attachment_ids", []):
                await hub.broadcast(item["opportunity_id"], {
                    "type": "delete_attachment",
                    "attachment_id": att_id,
                })

        return results
    finally:
        repo.close()
        feed_repo.close()
        flow_card_repo.close()
