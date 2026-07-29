"""基准配置 API（引用 parts_master + 底盘件清单）"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from app.repository.base_config_repo import BaseConfigRepository

router = APIRouter(prefix="/api/base-configs", tags=["base-configs"])


@router.get("")
def list_configs(series: Optional[str] = None, form: Optional[str] = None, bays: Optional[int] = None):
    cfgs = BaseConfigRepository().list(series, form, bays)
    return {"configs": cfgs, "total": len(cfgs)}


@router.get("/series")
def list_series():
    """返回所有机型系列（从 system_config.server_series 读取，全平台唯一权威源）。
    items 带 label 供下拉显示；series 为纯 value 数组，向后兼容老调用方。"""
    from app.repository.system_config_repo import SystemConfigRepository
    raw = SystemConfigRepository().get_value("server_series", [])
    items = [it for it in raw if isinstance(it, dict) and "value" in it] if isinstance(raw, list) else []
    return {"series": [it["value"] for it in items], "items": items}


@router.get("/forms")
def list_forms():
    """返回所有机箱形态（DISTINCT base_configs.form，数据驱动）。
    供需求分析词表编辑器「机型词表·form 字段」左侧下拉用。"""
    return {"forms": BaseConfigRepository().list_forms()}


@router.get("/{config_id}")
def get_config(config_id: int):
    c = BaseConfigRepository().get_with_parts(config_id)
    if not c:
        raise HTTPException(404, "基准配置不存在")
    return c


@router.post("")
def create_config(data: dict):
    try:
        return {"id": BaseConfigRepository().insert(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{config_id}")
def update_config(config_id: int, updates: dict):
    BaseConfigRepository().update(config_id, updates)
    return {"ok": True}


@router.delete("/{config_id}")
def delete_config(config_id: int):
    BaseConfigRepository().delete(config_id)
    return {"ok": True}


@router.put("/{config_id}/parts")
def set_parts(config_id: int, parts: List[dict]):
    """整体替换底盘件清单（基准配置组装）"""
    BaseConfigRepository().set_parts(config_id, parts)
    return {"ok": True}
