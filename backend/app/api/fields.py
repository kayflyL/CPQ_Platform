"""Unified field API - centralized field definitions"""
from fastapi import APIRouter, HTTPException, Query
from ..services.unified_field_service import UnifiedFieldService

router = APIRouter(prefix="/api/fields", tags=["fields"])


@router.get("/scope/{scope}")
def get_fields_by_scope(scope: str):
    """
    按业务域获取字段
    scope: opportunity / config / pricing / export / parse / system
    """
    service = UnifiedFieldService()
    try:
        fields = service.get_fields_by_scope(scope)
        return {"success": True, "data": fields, "count": len(fields)}
    finally:
        service.close()


@router.get("/page/{page}")
def get_fields_by_page(page: str):
    """
    按页面获取字段（基于 used_in_pages 字段）
    page: opportunity_detail / export_template / workbench / parse_template / ...
    """
    service = UnifiedFieldService()
    try:
        fields = service.get_fields_by_page(page)
        return {"success": True, "data": fields, "count": len(fields)}
    finally:
        service.close()


@router.get("/dynamic-sources")
def get_dynamic_source_fields(source_key: str = Query(None)):
    """
    获取动态数据源子字段
    source_key: l6_details / kp_details / warranty_details / config_summary
    如果不传 source_key，返回所有数据源的所有字段（按数据源分组）
    """
    service = UnifiedFieldService()
    try:
        fields = service.get_dynamic_source_fields(source_key)
        return {"success": True, "data": fields}
    finally:
        service.close()


@router.get("/type-keywords")
def get_type_keywords():
    """
    获取部件类型关键词映射
    用于替代 template_filler.py 和 pricing_engine.py 的硬编码
    """
    service = UnifiedFieldService()
    try:
        keywords = service.get_type_keywords()
        return {"success": True, "data": keywords}
    finally:
        service.close()


@router.get("/component-mapping")
def get_component_mapping():
    """
    获取组件映射
    用于替代 template_filler.py 的硬编码
    """
    service = UnifiedFieldService()
    try:
        mapping = service.get_component_mapping()
        return {"success": True, "data": mapping}
    finally:
        service.close()
