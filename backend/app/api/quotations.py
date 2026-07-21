"""Quotation API endpoints."""
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.repository.quotation_repo import QuotationRepository
from app.repository.opportunity_repo import OpportunityRepository

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


@router.get("")
def list_quotations(opportunity_id: Optional[str] = None, include_deleted: bool = False):
    """List all quotations, optionally filtered by opportunity_id."""
    repo = QuotationRepository()
    try:
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
        return {"quotations": [q.to_dict() for q in quotations]}
    finally:
        repo.close()


@router.get("/{quotation_id}")
def get_quotation(quotation_id: str, reparse: bool = False):
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
        
        # Include opportunity info (opportunity_name, customer_name)
        opportunity = opp_repo.get_opportunity(quotation.opportunity_id)
        if opportunity:
            result["opportunity_name"] = opportunity.get("opportunity_name", "") or ""
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

        return result
    finally:
        repo.close()
        opp_repo.close()


@router.post("")
def create_quotation(req: QuotationCreate):
    """Create a new quotation."""
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
def update_quotation(quotation_id: str, req: QuotationUpdate):
    """Update a quotation."""
    repo = QuotationRepository()
    try:
        update_data = req.dict(exclude_unset=True)
        quotation = repo.update(quotation_id, **update_data)
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"quotation": quotation.to_dict()}
    finally:
        repo.close()


@router.delete("/{quotation_id}")
def delete_quotation(quotation_id: str):
    """Soft delete a quotation."""
    repo = QuotationRepository()
    try:
        success = repo.delete(quotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"message": "Quotation deleted"}
    finally:
        repo.close()


@router.post("/{quotation_id}/set-primary")
def set_primary_quotation(quotation_id: str):
    """Set a quotation as primary (is_primary=True) and clear others for the same opportunity."""
    repo = QuotationRepository()
    try:
        success = repo.set_primary(quotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Quotation not found")
        return {"message": "Quotation set as primary"}
    finally:
        repo.close()


@router.post("/{quotation_id}/restore")
def restore_quotation(quotation_id: str):
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
def get_quotation_items(quotation_id: str):
    """Get all items for a quotation."""
    repo = QuotationRepository()
    try:
        items = repo.get_items(quotation_id)
        return {"items": [item.to_dict() for item in items]}
    finally:
        repo.close()


@router.post("/{quotation_id}/items")
def save_quotation_items(quotation_id: str, data: dict):
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

        count = repo.save_items(quotation_id, items)

        # Update config-level fields if provided
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
        if update_kwargs:
            repo.update(quotation_id, **update_kwargs)
        
        return {"saved": count}
    finally:
        repo.close()


# ── Batch Operations ──

class BatchQuotationRequest(BaseModel):
    quotation_ids: List[str]


@router.post("/batch-delete")
def batch_delete_quotations(req: BatchQuotationRequest):
    """批量软删除报价单"""
    repo = QuotationRepository()
    results = {"success": [], "failed": []}
    try:
        for qid in req.quotation_ids:
            try:
                repo.delete(qid)
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})
        return results
    finally:
        repo.close()


@router.post("/batch-restore")
def batch_restore_quotations(req: BatchQuotationRequest):
    """批量恢复报价单"""
    repo = QuotationRepository()
    results = {"success": [], "failed": []}
    try:
        for qid in req.quotation_ids:
            try:
                repo.restore(qid)
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})
        return results
    finally:
        repo.close()


@router.post("/batch-permanent-delete")
def batch_permanent_delete_quotations(req: BatchQuotationRequest):
    """批量永久删除报价单"""
    from app.models.quotation import Quotation
    from app.models.opportunity_item import OpportunityItem
    from app.models.base import Opportunity_SessionLocal
    from sqlalchemy import delete

    session = Opportunity_SessionLocal()
    results = {"success": [], "failed": []}
    try:
        for qid in req.quotation_ids:
            try:
                # Delete items first
                session.execute(
                    delete(OpportunityItem).where(OpportunityItem.quotation_id == qid)
                )
                # Delete quotation
                session.execute(
                    delete(Quotation).where(Quotation.quotation_id == qid)
                )
                results["success"].append(qid)
            except Exception as e:
                results["failed"].append({"id": qid, "error": str(e)})
        session.commit()
        return results
    finally:
        session.close()