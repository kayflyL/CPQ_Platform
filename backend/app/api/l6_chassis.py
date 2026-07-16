"""L6 机箱库 API 路由"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.repository.l6_chassis_repo import L6ChassisRepository

router = APIRouter(prefix="/api/l6-chassis", tags=["l6-chassis"])


# ========== 基准配置库 ==========

@router.get("/base-configs/distinct-values")
def get_distinct_values():
    """获取基准配置各维度的去重值（用于级联筛选）"""
    repo = L6ChassisRepository()
    try:
        return repo.get_distinct_values()
    finally:
        repo.close()


@router.get("/base-configs")
def list_base_configs(
    chassis: Optional[str] = None,
    chassis_series: Optional[str] = None,
    drive_bays: Optional[str] = None,
    backplane_type: Optional[str] = None,
):
    """获取基准配置列表，支持多维度筛选"""
    repo = L6ChassisRepository()
    try:
        configs = repo.get_base_configs(chassis, chassis_series, drive_bays, backplane_type)
        return {"configs": configs, "total": len(configs)}
    finally:
        repo.close()


@router.get("/base-configs/{config_id}")
def get_base_config(config_id: int):
    """获取单个基准配置（含组件清单）"""
    repo = L6ChassisRepository()
    try:
        config = repo.get_base_config_with_parts(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")
        return config
    finally:
        repo.close()


@router.post("/base-configs")
def create_base_config(data: dict):
    """新增基准配置"""
    required = ["chassis", "chassis_series"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
    
    repo = L6ChassisRepository()
    try:
        config_id = repo.insert_base_config(data)
        return {"config_id": config_id, "message": "创建成功"}
    finally:
        repo.close()


@router.put("/base-configs/{config_id}")
def update_base_config(config_id: int, data: dict):
    """更新基准配置"""
    repo = L6ChassisRepository()
    try:
        success = repo.update_base_config(config_id, data)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")
        return {"message": "更新成功"}
    finally:
        repo.close()


@router.delete("/base-configs/{config_id}")
def delete_base_config(config_id: int):
    """删除基准配置（含组件）"""
    repo = L6ChassisRepository()
    try:
        success = repo.delete_base_config(config_id)
        if not success:
            raise HTTPException(status_code=400, detail="删除失败")
        return {"message": "删除成功"}
    finally:
        repo.close()


# ========== 基准配置组件 ==========

@router.get("/base-configs/{config_id}/parts")
def list_base_config_parts(config_id: int):
    """获取基准配置的组件清单"""
    repo = L6ChassisRepository()
    try:
        parts = repo.get_base_config_parts(config_id)
        return {"parts": parts, "total": len(parts)}
    finally:
        repo.close()


@router.post("/base-config-parts")
def create_base_config_part(data: dict):
    """新增组件"""
    required = ["config_id", "part_name"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
    
    repo = L6ChassisRepository()
    try:
        part_id = repo.insert_base_config_part(data)
        return {"part_id": part_id, "message": "创建成功"}
    finally:
        repo.close()


@router.put("/base-config-parts/{part_id}")
def update_base_config_part(part_id: int, data: dict):
    """更新组件"""
    repo = L6ChassisRepository()
    try:
        success = repo.update_base_config_part(part_id, data)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")
        return {"message": "更新成功"}
    finally:
        repo.close()


@router.delete("/base-config-parts/{part_id}")
def delete_base_config_part(part_id: int):
    """删除组件"""
    repo = L6ChassisRepository()
    try:
        success = repo.delete_base_config_part(part_id)
        if not success:
            raise HTTPException(status_code=400, detail="删除失败")
        return {"message": "删除成功"}
    finally:
        repo.close()


# ========== 前面板线缆库 ==========

@router.get("/front-panel")
def list_front_panel_items(
    drive_bays: Optional[str] = None,
    backplane_type: Optional[str] = None,
):
    """获取前面板线缆列表，按属性维度过滤"""
    repo = L6ChassisRepository()
    try:
        items = repo.get_front_panel_items(drive_bays, backplane_type)
        return {"items": items, "total": len(items)}
    finally:
        repo.close()


@router.post("/front-panel")
def create_front_panel_item(data: dict):
    """新增前面板线缆"""
    required = ["cable_type", "part_name"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
    
    repo = L6ChassisRepository()
    try:
        item_id = repo.insert_front_panel_item(data)
        return {"item_id": item_id, "message": "创建成功"}
    finally:
        repo.close()


@router.put("/front-panel/{item_id}")
def update_front_panel_item(item_id: int, data: dict):
    """更新前面板线缆"""
    repo = L6ChassisRepository()
    try:
        success = repo.update_front_panel_item(item_id, data)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")
        return {"message": "更新成功"}
    finally:
        repo.close()


@router.delete("/front-panel/{item_id}")
def delete_front_panel_item(item_id: int):
    """删除前面板线缆"""
    repo = L6ChassisRepository()
    try:
        success = repo.delete_front_panel_item(item_id)
        if not success:
            raise HTTPException(status_code=400, detail="删除失败")
        return {"message": "删除成功"}
    finally:
        repo.close()


# ========== 后面板硬盘库 ==========

@router.get("/rear-panel")
def list_rear_panel_items(
    chassis: Optional[str] = None,
    backplane_type: Optional[str] = None,
):
    """获取后面板选项列表，按属性维度过滤"""
    repo = L6ChassisRepository()
    try:
        items = repo.get_rear_panel_items(chassis, backplane_type)
        return {"items": items, "total": len(items)}
    finally:
        repo.close()


@router.post("/rear-panel")
def create_rear_panel_item(data: dict):
    """新增后面板选项"""
    required = ["option_type", "part_name"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
    
    repo = L6ChassisRepository()
    try:
        item_id = repo.insert_rear_panel_item(data)
        return {"item_id": item_id, "message": "创建成功"}
    finally:
        repo.close()


@router.put("/rear-panel/{item_id}")
def update_rear_panel_item(item_id: int, data: dict):
    """更新后面板选项"""
    repo = L6ChassisRepository()
    try:
        success = repo.update_rear_panel_item(item_id, data)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")
        return {"message": "更新成功"}
    finally:
        repo.close()


@router.delete("/rear-panel/{item_id}")
def delete_rear_panel_item(item_id: int):
    """删除后面板选项"""
    repo = L6ChassisRepository()
    try:
        success = repo.delete_rear_panel_item(item_id)
        if not success:
            raise HTTPException(status_code=400, detail="删除失败")
        return {"message": "删除成功"}
    finally:
        repo.close()


# ========== 电源库 ==========

@router.get("/psu")
def list_psu_options(chassis_type: Optional[str] = None):
    """获取PSU选项列表"""
    repo = L6ChassisRepository()
    try:
        items = repo.get_psu_options(chassis_type)
        return {"items": items, "total": len(items)}
    finally:
        repo.close()


@router.post("/psu")
def create_psu_option(data: dict):
    """新增PSU选项"""
    required = ["wattage", "part_name"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
    
    repo = L6ChassisRepository()
    try:
        psu_id = repo.insert_psu_option(data)
        return {"psu_id": psu_id, "message": "创建成功"}
    finally:
        repo.close()


@router.put("/psu/{psu_id}")
def update_psu_option(psu_id: int, data: dict):
    """更新PSU选项"""
    repo = L6ChassisRepository()
    try:
        success = repo.update_psu_option(psu_id, data)
        if not success:
            raise HTTPException(status_code=400, detail="更新失败")
        return {"message": "更新成功"}
    finally:
        repo.close()


@router.delete("/psu/{psu_id}")
def delete_psu_option(psu_id: int):
    """删除PSU选项"""
    repo = L6ChassisRepository()
    try:
        success = repo.delete_psu_option(psu_id)
        if not success:
            raise HTTPException(status_code=400, detail="删除失败")
        return {"message": "删除成功"}
    finally:
        repo.close()
