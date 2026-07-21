import logging
import json

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
    """返回可用的元数据字段列表（从 BusinessField 表动态查询）"""
    repo = BusinessFieldRepository()
    try:
        fields = repo.list_enabled()
        return {"fields": [f["key"] for f in fields]}
    finally:
        repo.close()

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


# ================== KP Parts 完整 CRUD API (新表) ==================

@router.get("/kp/parts")
def list_parts(category_id: int = None, search: str = "", page: int = 1, page_size: int = 20,
               sort_by: str = "name", sort_order: str = "asc",
               brands: str = None, price_filter: str = None, specs: str = None):
    """分页列出配件（支持品牌/价格记录/规格筛选）"""
    repo = KPRepository()
    try:
        return repo.list_parts(category_id, search, page, page_size, sort_by, sort_order,
                               brands, price_filter, specs)
    finally:
        repo.close()


@router.get("/kp/brands")
def list_brands(category_id: int = None):
    """品牌列表 + 计数（用于筛选面板）"""
    repo = KPRepository()
    try:
        return {"brands": repo.list_brands(category_id)}
    finally:
        repo.close()


@router.get("/kp/spec-facets")
def list_spec_facets(category_id: int = None):
    """规格维度聚合（用于筛选面板，随分类变化）"""
    repo = KPRepository()
    try:
        return {"facets": repo.list_spec_facets(category_id)}
    finally:
        repo.close()


@router.get("/kp/parts/{part_id}")
def get_part(part_id: int):
    """获取配件详情（含规格、价格历史、兼容机型）"""
    repo = KPRepository()
    try:
        part = repo.get_part(part_id)
        if not part:
            raise HTTPException(status_code=404, detail="配件不存在")
        return part
    finally:
        repo.close()


@router.post("/kp/parts")
def create_part(data: dict):
    """创建配件"""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="配件名称不能为空")
    repo = KPRepository()
    try:
        return repo.create_part(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.close()


@router.put("/kp/parts/{part_id}")
def update_part(part_id: int, data: dict):
    """更新配件"""
    repo = KPRepository()
    try:
        part = repo.update_part(part_id, data)
        if not part:
            raise HTTPException(status_code=404, detail="配件不存在")
        return part
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.close()


@router.delete("/kp/parts/{part_id}")
def delete_part(part_id: int):
    """删除配件"""
    repo = KPRepository()
    try:
        ok = repo.delete_part(part_id)
        if not ok:
            raise HTTPException(status_code=404, detail="配件不存在")
        return {"status": "success"}
    finally:
        repo.close()


# ---- 分类管理 ----
@router.get("/kp/categories/all")
def list_all_categories():
    """列出所有分类（含层级信息）"""
    repo = KPRepository()
    try:
        return {"categories": repo.list_categories()}
    finally:
        repo.close()


@router.post("/kp/categories")
def create_category(data: dict):
    """创建分类"""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="分类名称不能为空")
    repo = KPRepository()
    try:
        return repo.create_category(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.close()


@router.put("/kp/categories/{cat_id}")
def update_category(cat_id: int, data: dict):
    """更新分类"""
    repo = KPRepository()
    try:
        cat = repo.update_category(cat_id, data)
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")
        return cat
    finally:
        repo.close()


@router.delete("/kp/categories/{cat_id}")
def delete_category(cat_id: int):
    """删除分类"""
    repo = KPRepository()
    try:
        ok = repo.delete_category(cat_id)
        if not ok:
            raise HTTPException(status_code=404, detail="分类不存在")
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        repo.close()


# ---- 价格历史 ----
@router.get("/kp/parts/{part_id}/prices")
def get_part_prices(part_id: int):
    """获取配件价格历史"""
    repo = KPRepository()
    try:
        part = repo.get_part(part_id)
        if not part:
            raise HTTPException(status_code=404, detail="配件不存在")
        return {"prices": part.get("price_history", [])}
    finally:
        repo.close()


@router.post("/kp/parts/{part_id}/prices")
def add_price(part_id: int, data: dict):
    """添加价格记录"""
    if data.get("price") is None:
        raise HTTPException(status_code=400, detail="价格不能为空")
    repo = KPRepository()
    try:
        return repo.add_price_history(
            part_id=part_id,
            price=data["price"],
            currency=data.get("currency", "RMB"),
            price_date=data.get("price_date"),
            note=data.get("note", ""),
            source=data.get("source", ""),
        )
    finally:
        repo.close()


@router.put("/kp/prices/{price_id}")
def update_price(price_id: int, data: dict):
    """更新价格记录"""
    repo = KPRepository()
    try:
        ok = repo.update_price_history(
            price_id=price_id,
            price=data.get("price"),
            price_date=data.get("price_date"),
            note=data.get("note"),
        )
        if not ok:
            raise HTTPException(status_code=404, detail="价格记录不存在")
        return {"ok": True}
    finally:
        repo.close()


@router.delete("/kp/prices/{price_id}")
def delete_price(price_id: int):
    """删除价格记录"""
    repo = KPRepository()
    try:
        ok = repo.delete_price_history(price_id)
        if not ok:
            raise HTTPException(status_code=404, detail="价格记录不存在")
        return {"ok": True}
    finally:
        repo.close()


# ---- 关联配件 ----
@router.get("/kp/parts/{part_id}/related")
def get_related_parts(part_id: int):
    """获取关联配件"""
    repo = KPRepository()
    try:
        return {"related": repo.list_related(part_id)}
    finally:
        repo.close()


@router.post("/kp/parts/{part_id}/related")
def add_related_part(part_id: int, data: dict):
    """添加关联配件"""
    if not data.get("target_part_id"):
        raise HTTPException(status_code=400, detail="缺少 target_part_id")
    repo = KPRepository()
    try:
        return repo.add_related(part_id, data["target_part_id"], data.get("sort_order", 0))
    finally:
        repo.close()


@router.delete("/kp/related/{relation_id}")
def remove_related_part(relation_id: int):
    """删除关联"""
    repo = KPRepository()
    try:
        ok = repo.remove_related(relation_id)
        if not ok:
            raise HTTPException(status_code=404, detail="关联不存在")
        return {"status": "success"}
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
    record_id = data.get("id")
    if not record_id:
        raise HTTPException(status_code=400, detail="Missing record ID")

    repo = L6Repository()
    try:
        updates = {k: v for k, v in data.items() if k != "id"}
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
# Core endpoints: GET list, POST create, PUT update, DELETE
# Import/Export: GET export, POST import
#
# Deprecated (backend tool-layer only, not used by frontend):
#   references, history, validation, usage-stats, sort-order, force-delete

from app.repository.business_field_repo import BusinessFieldRepository


@router.get("/business-fields")
def list_business_fields():
    """列出所有业务字段，包括静态字段和动态字段，并标注使用位置"""
    repo = BusinessFieldRepository()
    try:
        fields = repo.list_all()

        # 添加动态字段
        from app.models.dynamic_source_field import DynamicSourceField
        from app.models.base import Rules_SessionLocal
        rules_session = Rules_SessionLocal()
        try:
            dynamic_fields = rules_session.query(DynamicSourceField).order_by(
                DynamicSourceField.source_key, DynamicSourceField.sort_order
            ).all()

            for df in dynamic_fields:
                source_key = df.source_key
                field_key = df.field_key
                full_key = f"{source_key}.{field_key}"
                fields.append({
                    "key": full_key,
                    "label": df.field_label,
                    "category": "dynamic",
                    "group_name": source_key,
                    "source": "dynamic",
                    "scope": "all",
                    "enabled": bool(df.enabled),
                    "description": f"动态字段: {full_key}",
                    "used_in_pages": "[]",
                })
        finally:
            rules_session.close()

        return fields
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
    """删除业务字段"""
    repo = BusinessFieldRepository()
    try:
        if not repo.delete(field_key, operator):
            raise HTTPException(status_code=404, detail=f"Field '{field_key}' not found")
        return {"success": True}
    finally:
        repo.close()


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
    fields_list = data.get("fields", [])
    if not fields_list:
        raise HTTPException(status_code=400, detail="Missing fields array")

    mode = data.get("mode", "skip")
    if mode not in ("skip", "overwrite"):
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'skip' or 'overwrite'")

    repo = BusinessFieldRepository()
    try:
        result = repo.import_fields(fields_list, mode, operator)
        return result
    finally:
        repo.close()


# ================== Deprecated Endpoints ==================
# The following endpoints are kept for backend tool-layer use only.
# The frontend no longer calls them.

# @router.get("/business-fields/{field_key}/references")      # deprecated
# @router.post("/business-fields/{field_key}/references")     # deprecated
# @router.delete("/business-fields/{field_key}/references/..")# deprecated
# @router.post("/business-fields/check-references")           # deprecated
# @router.get("/business-fields/{field_key}/history")         # deprecated
# @router.post("/business-fields/{field_key}/validate")       # deprecated
# @router.post("/business-fields/validate-batch")             # deprecated
# @router.get("/business-fields/{field_key}/stats")           # deprecated
# @router.get("/business-fields-usage-stats")                 # deprecated
# @router.post("/business-fields/{field_key}/record-usage")   # deprecated
# @router.post("/business-fields/record-usage-batch")         # deprecated
# @router.put("/business-fields/sort-order")                  # deprecated
# @router.delete("/business-fields/{field_key}/force")        # deprecated
