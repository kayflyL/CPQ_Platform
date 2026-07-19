"""KP 核心配件查询接口 — 面向 ConfigWizard 和 derive。

从 kp.kp_parts + kp.kp_categories + kp.kp_price_history 查询，
输出格式对齐 ConfigWizard 和 derive 需要的字段。
"""
from fastapi import APIRouter, Query
from sqlalchemy import text
from typing import List, Optional
from app.models.base import kp_engine

router = APIRouter(prefix="/api/kp", tags=["kp"])


@router.get("/categories")
def list_categories():
    """返回所有 KP 分类列表"""
    with kp_engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, name FROM kp.kp_categories ORDER BY sort_order, id"
        )).mappings().all()
    return [dict(r) for r in rows]


@router.get("/parts")
def list_parts(category_id: Optional[int] = Query(None, description="分类ID"),
               series: Optional[str] = Query(None, description="机型系列，按 applicable.series 过滤")):
    """返回 KP 配件列表，可按 category_id / series 筛选。

    series 过滤语义：applicable 为 null 或无 series 键 = 全系列通用（返回）；
    applicable.series 含该系列 = 返回；applicable.series=[] = 隐藏。
    输出格式：pn/name/category/brand/sub_type/specs/applicable/unit_price。
    """
    q = """
        SELECT
            p.id,
            COALESCE(NULLIF(p.oem_sku, ''), p.name) AS pn,
            p.name,
            c.name AS category,
            p.brand,
            '' AS sub_type,
            '{}'::jsonb AS specs,
            p.applicable,
            COALESCE(ph.price, 0) AS unit_price
        FROM kp.kp_parts p
        JOIN kp.kp_categories c ON p.category_id = c.id
        LEFT JOIN LATERAL (
            SELECT price
            FROM kp.kp_price_history
            WHERE part_id = p.id
            ORDER BY price_date DESC
            LIMIT 1
        ) ph ON true
    """
    params = {}
    where = []
    if category_id is not None:
        where.append("p.category_id = :cid")
        params["cid"] = category_id
    if series:
        where.append("(p.applicable IS NULL OR p.applicable->'series' IS NULL OR p.applicable->'series' ? :series)")
        params["series"] = series
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY c.sort_order, p.name"
    
    with kp_engine.connect() as c:
        rows = c.execute(text(q), params).mappings().all()
    
    out = []
    for r in rows:
        d = dict(r)
        # specs 从 kp_part_specs 聚合（当前表为空，先返回空 dict）
        d["specs"] = {}
        out.append(d)
    return out


@router.get("/parts/by-pn/{pn}")
def get_part_by_pn(pn: str):
    """按料号查单个 KP（供 derive 用）"""
    q = """
        SELECT
            p.oem_sku AS pn,
            p.name,
            c.name AS category,
            p.brand,
            '' AS sub_type,
            '{}'::jsonb AS specs,
            p.applicable,
            COALESCE(ph.price, 0) AS unit_price
        FROM kp.kp_parts p
        JOIN kp.kp_categories c ON p.category_id = c.id
        LEFT JOIN LATERAL (
            SELECT price
            FROM kp.kp_price_history
            WHERE part_id = p.id
            ORDER BY price_date DESC
            LIMIT 1
        ) ph ON true
        WHERE p.oem_sku = :pn
    """
    with kp_engine.connect() as c:
        row = c.execute(text(q), {"pn": pn}).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["specs"] = {}
    return d
