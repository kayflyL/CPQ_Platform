from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel
from app.services.quote_service import QuoteService
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.feed_repo import FeedRepository
from app.services.storage_adapter import get_storage, build_object_id, StorageError
from app.services.feed_hub import hub
from app.api.feed import current_user


def _decode_filename(filename: str) -> str:
    """Best-effort fix for Windows multipart form encoding of Chinese filenames.

    multipart filenames sometimes arrive latin1-mangled on Windows; try common
    encodings and keep the first decode that yields CJK chars.
    """
    try:
        if not filename.isascii():
            return filename
        for encoding in ("utf-8", "gbk", "gb2312", "latin1"):
            try:
                decoded = filename.encode("latin1").decode(encoding)
                if decoded != filename and any("一" <= c <= "鿿" for c in decoded):
                    return decoded
            except Exception:
                continue
    except Exception:
        pass
    return filename


router = APIRouter(
    prefix="/api/quote",
    tags=["quote"]
)


@router.post("/upload-to-opportunity")
async def upload_to_opportunity(
    file: UploadFile = File(...),
    opportunity_id: str = Form(...),
    user: dict = Depends(current_user),
):
    """Upload Excel quotation to a specific opportunity.

    Parses the file, creates a quotation record, and archives the source Excel
    into the opportunity's file index so it shows up in the archive view.
    """
    # Verify opportunity exists
    opp_repo = OpportunityRepository()
    try:
        opportunity = opp_repo.get_opportunity(opportunity_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="商机不存在")
        customer_name = opportunity.get("customer_name", "") or ""
    finally:
        opp_repo.close()

    filename = _decode_filename(file.filename or "")
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 文件")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，最大允许 50MB")

    service = QuoteService()
    storage = get_storage()
    feed_repo = FeedRepository()
    try:
        result = service.process_upload(content, filename)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        # Archive the source Excel under opportunities/{opp_id}/
        ext = Path(filename).suffix.lower()
        object_id = build_object_id(filename)
        try:
            storage_key = storage.save_bytes(opportunity_id, object_id, content, ext, customer_name=customer_name)
        except StorageError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Create quotation pointing at the archived file (stable, unlike _temp/)
        from app.repository.quotation_repo import QuotationRepository
        quo_repo = QuotationRepository()
        try:
            quotation = quo_repo.create(
                opportunity_id=opportunity_id,
                file_path=storage_key,
            )

            # Persist parsed items (save_items deletes existing first, so save all at once)
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

            # 持久化 excel 参考快照（L6 + KP 行）到 config_l6_picks：左栏 BomTable 与
            # 规格书导出同源 bom_excel_rows。L6 行不计价（items 不含 L6），故不会与
            # 规格书的 items 回落重复——preview_data_loader 的 covered_cfgs 判定去重。
            config_l6_picks = {}
            for cfg_name, cfg_data in configs.items():
                bom_rows = cfg_data.get("bom_excel_rows")
                if bom_rows:
                    config_l6_picks[cfg_name] = {
                        "bom_source": "excel",
                        "bom_excel_rows": bom_rows,
                    }
            if config_l6_picks:
                quo_repo.update(quotation.quotation_id, config_l6_picks=config_l6_picks)
        finally:
            quo_repo.close()

        # Index the archived file so it appears in the opportunity archive view
        mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if ext == ".xlsx"
            else "application/vnd.ms-excel"
        )
        att = feed_repo.add_attachment(
            opportunity_id=opportunity_id,
            uploader_user_id=user["user_id"],
            original_filename=filename,
            storage_key=storage_key,
            file_size=len(content),
            mime_type=mime,
            kind="upload",
            quotation_id=quotation.quotation_id,
            category="technical",
        )
        await hub.broadcast(opportunity_id, {"type": "attachment", "attachment": att})

        result["quotation_id"] = quotation.quotation_id
        result["attachment"] = att
        return result
    finally:
        service.close()
        feed_repo.close()


@router.get("/kp/history")
async def get_kp_price_history(model: str):
    """Get KP price history for a given model."""
    service = QuoteService()
    try:
        history = service.get_kp_history(model)
        return history
    finally:
        service.close()


class KpSyncPriceRequest(BaseModel):
    category: str
    model: str
    price: float
    currency: str = "RMB"
    note: str = "报价工作台手动同步"


@router.post("/kp/sync-price")
async def sync_kp_price(payload: KpSyncPriceRequest):
    """单条手动同步：把当前 KP 配件价格写入 kp_parts 价格历史。
    用户在报价工作台点击某 KP 卡片的「同步」按钮时调用（替代保存时自动批量同步）。"""
    service = QuoteService()
    try:
        service.engine.kp_repo.insert_price(
            payload.category,
            payload.model,
            float(payload.price),
            payload.currency,
            datetime.now().strftime("%Y-%m-%d"),
            payload.note or "报价工作台手动同步",
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败：{e}")
    finally:
        service.close()
