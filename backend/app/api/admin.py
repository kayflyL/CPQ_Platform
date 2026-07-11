import logging

logger = logging.getLogger(__name__)
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.repository.kp_repo import KPRepository
from app.repository.l6_repo import L6Repository

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"]
)

# ================== Metadata Fields API ==================

@router.get("/metadata-fields")
def list_metadata_fields():
    """返回可用的元数据字段列表"""
    return {
        "fields": [
            "opportunity_name", "model_name", "customer_name",
            "sales_person", "fae", "date", "total_qty",
            "platform_type", "chassis_form", "company",
            "l6_spec", "description", "model_qty"
        ]
    }

# ================== KP (Key Parts) APIs ==================

@router.get("/kp/categories")
def list_kp_categories():
    repo = KPRepository()
    try:
        return {"categories": repo.get_categories()}
    finally:
        repo.close()


@router.get("/kp/by-category")
def list_kp_by_category(category: str, search: str = ""):
    repo = KPRepository()
    try:
        items = repo.get_by_category(category, search)
        return {"items": items, "total": len(items)}
    finally:
        repo.close()


@router.post("/kp/rename")
def rename_kp_model(data: dict):
    old_model = data.get("old_model")
    new_model = data.get("new_model")
    if not old_model or not new_model:
        raise HTTPException(status_code=400, detail="Missing old_model or new_model")
    repo = KPRepository()
    try:
        repo.rename_model(old_model, new_model)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.post("/kp/update-note")
def update_kp_note(data: dict):
    model = data.get("model")
    note = data.get("note", "")
    if not model:
        raise HTTPException(status_code=400, detail="Missing model")
    repo = KPRepository()
    try:
        repo.update_note(model, note)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.get("/kp/list")
def list_kp(page: int = 1, page_size: int = 20, search: str = "", category: str = "", sort_by: str = "date", sort_order: str = "desc"):
    repo = KPRepository()
    try:
        all_items = repo.get_latest_prices(search, category, sort_by, sort_order)
        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_items[start:end]
        return {"items": page_items, "total": total}
    finally:
        repo.close()


@router.post("/kp/update")
def update_kp_price(data: dict):
    part_name = data.get("model") or data.get("part_name")
    price = data.get("price")
    spec = data.get("spec", "")
    category = data.get("category", "Key Parts")
    currency = data.get("currency", "RMB")
    note = data.get("note", "手动更新")

    if not part_name or price is None:
        raise HTTPException(status_code=400, detail="Missing model/part_name or price")

    repo = KPRepository()
    try:
        repo.insert_price(category, part_name, price, currency, note=note)
        return {"status": "success", "message": "Price updated"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.get("/kp/history")
def get_kp_history(model: str = None, part_name: str = None):
    target = model or part_name
    if not target:
        raise HTTPException(status_code=400, detail="Missing model or part_name")

    repo = KPRepository()
    try:
        history = repo.get_price_history(target)
        return history
    finally:
        repo.close()


# ================== L6 Whole Machine APIs ==================

@router.get("/l6/list")
def list_l6(page: int = 1, page_size: int = 20, search: str = ""):
    repo = L6Repository()
    try:
        items, total = repo.get_all_records(search, page, page_size)
        return {"items": items, "total": total}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}
    finally:
        repo.close()


@router.post("/l6/update")
def update_l6(data: dict):
    record_id = data.get("id") or data.get("rowid")
    if not record_id:
        raise HTTPException(status_code=400, detail="Missing record ID")

    repo = L6Repository()
    try:
        updates = {k: v for k, v in data.items() if k not in ("id", "rowid")}
        repo.update_record(int(record_id), updates)
        
        # 如果更新了价格，写入历史快照
        if "price" in updates:
            note = updates.get("note", "")
            repo.save_history_snapshot(int(record_id), float(updates["price"]), note)
        
        return {"status": "success", "message": "L6 record updated"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.get("/l6/grouped")
def list_l6_grouped(search: str = ""):
    """获取按机型聚合的L6数据"""
    repo = L6Repository()
    try:
        groups = repo.get_grouped_by_model(search)
        return {"groups": groups, "total": len(groups)}
    except Exception as e:
        return {"groups": [], "total": 0, "error": str(e)}
    finally:
        repo.close()


@router.post("/l6/create")
def create_l6(data: dict):
    """新增L6记录"""
    required_fields = ["chassis", "model", "price"]
    for field in required_fields:
        if field not in data or data[field] is None:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    repo = L6Repository()
    try:
        # 设置默认值
        record = {
            "chassis": data.get("chassis", ""),
            "model": data.get("model", ""),
            "motherboard": data.get("motherboard", ""),
            "backplane": data.get("backplane", ""),
            "gpu_expansion": data.get("gpu_expansion", ""),
            "psu": data.get("psu", ""),
            "drive_bays": data.get("drive_bays", ""),
            "rail_kit": data.get("rail_kit", ""),
            "power_cord": data.get("power_cord", ""),
            "price": float(data.get("price", 0)),
            "update_date": data.get("update_date") or datetime.now().strftime("%Y-%m-%d"),
            "note": data.get("note", ""),
        }
        new_id = repo.insert_record(record)
        
        # 写入历史快照
        if new_id:
            repo.save_history_snapshot(new_id, record["price"], record["note"])
        
        return {"status": "success", "message": "L6 record created", "id": new_id}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.delete("/l6/{record_id}")
def delete_l6(record_id: int):
    """删除L6记录"""
    repo = L6Repository()
    try:
        repo.delete_record(record_id)
        return {"status": "success", "message": "L6 record deleted"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.get("/l6/{record_id}/history")
def get_l6_history(record_id: int, limit: int = 50):
    """获取L6记录的价格历史"""
    repo = L6Repository()
    try:
        history = repo.get_history(record_id, limit)
        return {"history": history, "total": len(history)}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.put("/l6/sort-order")
def update_l6_sort_order(data: dict):
    """批量更新L6记录排序顺序"""
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Missing items array")
    
    repo = L6Repository()
    try:
        repo.batch_update_sort_order(items)
        return {"status": "success", "message": "Sort order updated"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


# ================== Business Fields Management ==================

from app.repository.business_field_repo import BusinessFieldRepository


@router.get("/business-fields")
def list_business_fields():
    """列出所有业务字段（含禁用）"""
    repo = BusinessFieldRepository()
    try:
        return repo.list_all()
    finally:
        repo.close()


@router.post("/business-fields")
def create_business_field(data: dict, operator: str = "system"):
    """新增业务字段"""
    required = ["key", "label", "category", "source"]
    for field in required:
        if field not in data or not data[field]:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    repo = BusinessFieldRepository()
    try:
        # 检查 key 是否已存在
        existing = repo.get_by_key(data["key"])
        if existing:
            raise HTTPException(status_code=409, detail=f"Field key '{data['key']}' already exists")
        return repo.create(data, operator)
    finally:
        repo.close()


@router.put("/business-fields/{field_key}")
def update_business_field(field_key: str, data: dict, operator: str = "system"):
    """更新业务字段"""
    repo = BusinessFieldRepository()
    try:
        result = repo.update(field_key, data, operator)
        if not result:
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        return result
    finally:
        repo.close()


@router.delete("/business-fields/{field_key}")
def delete_business_field(field_key: str, operator: str = "system"):
    """删除业务字段（含引用检查）"""
    repo = BusinessFieldRepository()
    try:
        # Check references first
        refs = repo.get_references(field_key)
        if refs:
            return {
                "success": False,
                "has_references": True,
                "references": refs,
                "message": f"该字段被 {len(refs)} 处引用，请先解除引用或确认强制删除"
            }
        
        if not repo.delete(field_key, operator):
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        return {"success": True}
    finally:
        repo.close()


@router.delete("/business-fields/{field_key}/force")
def force_delete_business_field(field_key: str, operator: str = "system"):
    """强制删除业务字段（忽略引用）"""
    repo = BusinessFieldRepository()
    try:
        if not repo.delete(field_key, operator):
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        return {"success": True, "message": "字段已强制删除"}
    finally:
        repo.close()


@router.put("/business-fields/sort-order")
def update_business_fields_sort(data: dict):
    """批量更新业务字段排序"""
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Missing items array")
    
    repo = BusinessFieldRepository()
    try:
        repo.batch_update_sort(items)
        return {"status": "success", "message": "Sort order updated"}
    finally:
        repo.close()


# ================== Field References ==================

@router.get("/business-fields/{field_key}/references")
def get_field_references(field_key: str):
    """获取字段引用关系"""
    repo = BusinessFieldRepository()
    try:
        refs = repo.get_references(field_key)
        return {"field_key": field_key, "references": refs, "total": len(refs)}
    finally:
        repo.close()


@router.post("/business-fields/{field_key}/references")
def add_field_reference(field_key: str, data: dict):
    """添加字段引用"""
    required = ["ref_type", "ref_id"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    repo = BusinessFieldRepository()
    try:
        # Check if field exists
        if not repo.get_by_key(field_key):
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        
        ref = repo.add_reference(
            field_key=field_key,
            ref_type=data["ref_type"],
            ref_id=data["ref_id"],
            ref_name=data.get("ref_name")
        )
        return ref
    finally:
        repo.close()


@router.delete("/business-fields/{field_key}/references/{ref_type}/{ref_id}")
def remove_field_reference(field_key: str, ref_type: str, ref_id: int):
    """删除字段引用"""
    repo = BusinessFieldRepository()
    try:
        if not repo.remove_reference(field_key, ref_type, ref_id):
            raise HTTPException(status_code=404, detail="Reference not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/business-fields/check-references")
def check_field_references(data: dict):
    """批量检查字段引用"""
    keys = data.get("keys", [])
    if not keys:
        raise HTTPException(status_code=400, detail="Missing keys array")
    
    repo = BusinessFieldRepository()
    try:
        refs = repo.check_references(keys)
        return {"references": refs, "total_fields_with_refs": len(refs)}
    finally:
        repo.close()


# ================== Field Audit History ==================

@router.get("/business-fields/{field_key}/history")
def get_field_history(field_key: str, limit: int = 50):
    """获取字段变更历史"""
    repo = BusinessFieldRepository()
    try:
        if not repo.get_by_key(field_key):
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        
        history = repo.get_audit_history(field_key, limit)
        return {"field_key": field_key, "history": history, "total": len(history)}
    finally:
        repo.close()


# ================== Field Validation ==================

@router.post("/business-fields/{field_key}/validate")
def validate_field_value(field_key: str, data: dict):
    """校验字段值"""
    if "value" not in data:
        raise HTTPException(status_code=400, detail="Missing value")
    
    repo = BusinessFieldRepository()
    try:
        result = repo.validate_field_value(field_key, data["value"])
        return result
    finally:
        repo.close()


@router.post("/business-fields/validate-batch")
def validate_field_values_batch(data: dict):
    """批量校验字段值"""
    values = data.get("values", {})  # {field_key: value}
    if not values:
        raise HTTPException(status_code=400, detail="Missing values")
    
    repo = BusinessFieldRepository()
    try:
        results = {}
        all_valid = True
        for key, value in values.items():
            result = repo.validate_field_value(key, value)
            results[key] = result
            if not result["valid"]:
                all_valid = False
        
        return {"valid": all_valid, "results": results}
    finally:
        repo.close()


# ================== Field Usage Stats ==================

@router.get("/business-fields/{field_key}/stats")
def get_field_stats(field_key: str):
    """获取字段使用统计"""
    repo = BusinessFieldRepository()
    try:
        stats = repo.get_usage_stats(field_key)
        if not stats:
            raise HTTPException(status_code=404, detail=f"Stats for field '{field_key}' not found")
        return stats
    finally:
        repo.close()


@router.get("/business-fields-usage-stats")
def get_all_field_stats():
    """获取所有字段使用统计"""
    repo = BusinessFieldRepository()
    try:
        stats = repo.get_all_usage_stats()
        return {"stats": stats, "total": len(stats)}
    finally:
        repo.close()


@router.post("/business-fields/{field_key}/record-usage")
def record_field_usage(field_key: str):
    """记录字段使用"""
    repo = BusinessFieldRepository()
    try:
        repo.record_usage(field_key)
        return {"success": True}
    finally:
        repo.close()


@router.post("/business-fields/record-usage-batch")
def record_field_usage_batch(data: dict):
    """批量记录字段使用"""
    keys = data.get("keys", [])
    if not keys:
        raise HTTPException(status_code=400, detail="Missing keys array")
    
    repo = BusinessFieldRepository()
    try:
        repo.record_batch_usage(keys)
        return {"success": True, "count": len(keys)}
    finally:
        repo.close()


# ================== Field Import/Export ==================

@router.get("/business-fields-export")
def export_business_fields(keys: str = None):
    """导出字段定义"""
    repo = BusinessFieldRepository()
    try:
        key_list = keys.split(",") if keys else None
        fields = repo.export_fields(key_list)
        return {"fields": fields, "total": len(fields), "exported_at": __import__('datetime').datetime.now().isoformat()}
    finally:
        repo.close()


@router.post("/business-fields-import")
def import_business_fields(data: dict, operator: str = "system"):
    """导入字段定义"""
    fields = data.get("fields", [])
    if not fields:
        raise HTTPException(status_code=400, detail="Missing fields array")
    
    mode = data.get("mode", "skip")  # skip or overwrite
    if mode not in ("skip", "overwrite"):
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'skip' or 'overwrite'")
    
    repo = BusinessFieldRepository()
    try:
        result = repo.import_fields(fields, mode, operator)
        return result
    finally:
        repo.close()
