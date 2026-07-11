from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional
from app.services.quote_service import QuoteService
from app.utils.file_storage import FileStorage
from app.repository.opportunity_file_repo import OpportunityFileRepository
from app.repository.opportunity_repo import OpportunityRepository
import uuid

router = APIRouter(
    prefix="/api/quote",
    tags=["quote"]
)

@router.post("/upload")
async def upload_and_parse(
    file: UploadFile = File(...),
    opportunity_id: Optional[str] = Form(None)
):
    """
    Uploads an Excel quotation file, parses it, enriches with L6/KP prices,
    and returns the structured JSON for the frontend to display.
    Saves file to temporary directory (will be moved to opportunity folder when opportunity is saved).
    
    If opportunity_id is not provided, a new one will be generated.
    """
    # Generate opportunity_id if not provided
    if not opportunity_id:
        opportunity_id = f"OPP_{uuid.uuid4().hex[:12].upper()}"
    
    # Case-insensitive check for Excel extensions
    filename = file.filename or ""
    
    # Fix Windows multipart form encoding issue for Chinese filenames
    try:
        # Try to decode as UTF-8 if it looks like garbled text
        if not filename.isascii():
            # Already contains non-ASCII, likely correct
            pass
        else:
            # Try common encodings
            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                try:
                    decoded = filename.encode('latin1').decode(encoding)
                    if decoded != filename and any('\u4e00' <= c <= '\u9fff' for c in decoded):
                        filename = decoded
                        break
                except:
                    continue
    except:
        pass
    
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，最大允许 50MB")

    # Save file to temporary directory (not opportunity folder yet)
    file_storage = FileStorage()
    file_info = file_storage.save_upload_temp(content, filename)
    
    # Parse the file
    service = QuoteService()
    try:
        result = service.process_upload(content, file.filename)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
        
        # Add opportunity_id and temp file info to result
        result['opportunity_id'] = opportunity_id
        result['temp_file'] = {
            'temp_path': file_info['temp_path'],
            'original_name': filename,
            'file_size': file_info['file_size']
        }
        return result
    finally:
        service.close()


@router.post("/upload-to-opportunity")
async def upload_to_opportunity(
    file: UploadFile = File(...),
    opportunity_id: str = Form(...)
):
    """Upload Excel quotation to a specific opportunity, parse and create quotation record."""
    # Verify opportunity exists
    opp_repo = OpportunityRepository()
    try:
        opportunity = opp_repo.get_opportunity(opportunity_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="商机不存在")
    finally:
        opp_repo.close()

    # Validate file type
    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 文件")

    content = await file.read()
    file_storage = FileStorage()
    file_info = file_storage.save_upload_temp(content, filename)

    service = QuoteService()
    try:
        result = service.process_upload(content, file.filename)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        # Create quotation record in the opportunity
        from app.repository.quotation_repo import QuotationRepository
        quo_repo = QuotationRepository()
        try:
            quotation = quo_repo.create(
                opportunity_id=opportunity_id,
                file_path=file_info['temp_path'],
            )

            # Persist parsed items so they're available when editing
            # Collect ALL items from all configs and save together
            # (save_items deletes existing items first, so must save all at once)
            configs = result.get("configs", {})
            all_items = []
            for cfg_name, cfg_data in configs.items():
                items = cfg_data.get("items", [])
                for item in items:
                    item_copy = dict(item)
                    item_copy["config_name"] = cfg_name
                    all_items.append(item_copy)
            if all_items:
                quo_repo.save_items(quotation.quotation_id, all_items)
        finally:
            quo_repo.close()

        # Return quotation_id + parsed data + temp_file info
        result["quotation_id"] = quotation.quotation_id
        result["temp_file"] = {
            "temp_path": file_info["temp_path"],
            "original_name": filename,
            "file_size": file_info["file_size"],
        }
        return result
    finally:
        service.close()


@router.post("/parse-preview")
async def parse_preview(
    file: UploadFile = File(...)
):
    """Parse uploaded Excel and return preview data (L6 match + KP items) WITHOUT creating a quotation.
    Used by the upload confirmation drawer."""
    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 文件")

    content = await file.read()
    file_storage = FileStorage()
    file_info = file_storage.save_upload_temp(content, filename)

    service = QuoteService()
    try:
        result = service.process_upload(content, file.filename)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        result['temp_file'] = {
            'temp_path': file_info['temp_path'],
            'original_name': filename,
            'file_size': file_info['file_size']
        }
        return result
    finally:
        service.close()


@router.post("/confirm-upload")
async def confirm_upload(
    file: UploadFile = File(...),
    opportunity_id: str = Form(...)
):
    """Confirm upload: parse, create quotation record, and return quotation_id.
    Called after user confirms L6/KP matching in the drawer."""
    opp_repo = OpportunityRepository()
    try:
        opportunity = opp_repo.get_opportunity(opportunity_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="商机不存在")
    finally:
        opp_repo.close()

    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 文件")

    content = await file.read()
    file_storage = FileStorage()
    file_info = file_storage.save_upload_temp(content, filename)

    service = QuoteService()
    try:
        result = service.process_upload(content, file.filename)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        from app.repository.quotation_repo import QuotationRepository
        quo_repo = QuotationRepository()
        try:
            quotation = quo_repo.create(
                opportunity_id=opportunity_id,
                file_path=file_info['temp_path'],
            )

            configs = result.get("configs", {})
            all_items = []
            for cfg_name, cfg_data in configs.items():
                items = cfg_data.get("items", [])
                for item in items:
                    item_copy = dict(item)
                    item_copy["config_name"] = cfg_name
                    all_items.append(item_copy)
            if all_items:
                quo_repo.save_items(quotation.quotation_id, all_items)
        finally:
            quo_repo.close()

        result["quotation_id"] = quotation.quotation_id
        result["temp_file"] = {
            "temp_path": file_info["temp_path"],
            "original_name": filename,
            "file_size": file_info["file_size"],
        }
        return result
    finally:
        service.close()


@router.get("/kp/history")
async def get_kp_price_history(model: str):
    """Get KP price history for a given model."""
    service = QuoteService()
    try:
        history = service.get_kp_history(model)
        return history
    finally:
        service.close()


@router.get("/l6/candidates")
async def get_l6_candidates(
    chassis: Optional[str] = None,
    model: Optional[str] = None,
    drive_bays: Optional[str] = None,
    psu: Optional[str] = None,
    motherboard: Optional[str] = None,
):
    """Get top 3 L6 candidates by match score for given dimensions."""
    from app.engine.pricing_engine import PricingEngine
    from app.repository.kp_repo import KPRepository
    from app.repository.l6_repo import L6Repository

    l6_repo = L6Repository()
    engine = PricingEngine(KPRepository(), l6_repo, OpportunityRepository())
    try:
        dim_values = {
            'chassis_form': chassis or '',
            'l6_model_type': model or '',
            'drive_bays': drive_bays or '',
            'psu': psu or '',
            'motherboard': motherboard or '',
        }
        l6_records = l6_repo.get_all_for_matching()
        if not l6_records:
            return {"candidates": []}

        import pandas as pd
        l6_df = pd.DataFrame(l6_records)

        # Score each record
        match_dims = engine._l6_match_dims
        total_dims = len(match_dims)
        scored = []
        for _, row in l6_df.iterrows():
            score = 0
            for dim in match_dims:
                val = dim_values.get(
                    'chassis_form' if dim == 'chassis' else
                    'l6_model_type' if dim == 'model' else dim, ''
                )
                if val and str(row.get(dim, '')).strip() == str(val).strip():
                    score += 1
            if score > 0:
                record = row.to_dict()
                record['match_score'] = int((score / total_dims) * 100) if total_dims > 0 else 0
                record['matched_dims'] = score
                record['total_dims'] = total_dims
                scored.append(record)

        scored.sort(key=lambda x: x['match_score'], reverse=True)
        top3 = scored[:3]
        return {"candidates": top3}
    finally:
        l6_repo.close()
