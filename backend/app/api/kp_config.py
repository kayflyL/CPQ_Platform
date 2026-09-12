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


@router.get("/spec-keys")
def list_spec_keys():
    """每个 KP 品类下现有的 spec_key 列表（DISTINCT，从 kp_part_specs 实际数据聚合）。
    供推理流 match_kp 规则编辑的字段下拉用。返回 {category: [spec_key, ...]}。"""
    with kp_engine.connect() as c:
        rows = c.execute(text("""
            SELECT DISTINCT c.name AS category, s.spec_key
            FROM kp.kp_part_specs s
            JOIN kp.kp_parts p ON s.part_id = p.id
            JOIN kp.kp_categories c ON p.category_id = c.id
            WHERE c.name IS NOT NULL AND s.spec_key IS NOT NULL AND s.spec_key <> ''
            ORDER BY c.name, s.spec_key
        """)).mappings().all()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["category"], []).append(r["spec_key"])
    return out


@router.get("/parts")
def list_parts(category_id: Optional[int] = Query(None, description="分类ID"),
               series: Optional[str] = Query(None, description="机型系列，按 applicable.series 过滤")):
    """返回 KP 配件列表，可按 category_id / series 筛选。

    series 过滤语义：applicable 为 null 或无 series 键 = 全系列通用（返回）；
    applicable.series 含该系列 = 返回；applicable.series=[] = 隐藏。
    输出格式：pn/name/category/brand/specs/applicable/unit_price。
    """
    q = """
        SELECT
            p.id,
            COALESCE(NULLIF(p.oem_sku, ''), p.name) AS pn,
            p.name,
            c.name AS category,
            p.brand,
            COALESCE(
              (SELECT jsonb_object_agg(s.spec_key, s.spec_value)
                 FROM kp.kp_part_specs s
                WHERE s.part_id = p.id AND s.spec_key IS NOT NULL),
              '{}'::jsonb
            ) AS specs,
            p.applicable,
            COALESCE(ph.price, 0) AS unit_price,
            ph.currency AS unit_currency,
            ph.price_date AS latest_price_date
        FROM kp.kp_parts p
        JOIN kp.kp_categories c ON p.category_id = c.id
        LEFT JOIN LATERAL (
            SELECT price, currency, price_date
            FROM kp.kp_price_history
            WHERE part_id = p.id
            ORDER BY price_date DESC NULLS LAST, id DESC
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
        out.append(dict(r))
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
            COALESCE(
              (SELECT jsonb_object_agg(s.spec_key, s.spec_value)
                 FROM kp.kp_part_specs s
                WHERE s.part_id = p.id AND s.spec_key IS NOT NULL),
              '{}'::jsonb
            ) AS specs,
            p.applicable,
            COALESCE(ph.price, 0) AS unit_price,
            ph.currency AS unit_currency,
            ph.price_date AS latest_price_date
        FROM kp.kp_parts p
        JOIN kp.kp_categories c ON p.category_id = c.id
        LEFT JOIN LATERAL (
            SELECT price, currency, price_date
            FROM kp.kp_price_history
            WHERE part_id = p.id
            ORDER BY price_date DESC NULLS LAST, id DESC
            LIMIT 1
        ) ph ON true
        WHERE p.oem_sku = :pn
    """
    with kp_engine.connect() as c:
        row = c.execute(text(q), {"pn": pn}).mappings().first()
    if not row:
        return None
    return dict(row)


# ── 检索别名（kp.kp_search_aliases；part_lexicon 词法引擎的口语词→库内词形映射） ──

@router.get("/search-aliases")
def list_search_aliases(enabled: Optional[bool] = Query(None)):
    """全部检索别名（enabled=None 全量，True 只看生效行）。"""
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        return repo.list_search_aliases(enabled_only=bool(enabled))
    finally:
        repo.close()


@router.put("/search-aliases")
def upsert_search_alias(body: dict):
    """新增/更新别名：{alias, expansion, note?}。expansion 为空格分隔 token（万兆→"10G"）。"""
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        return repo.upsert_search_alias(str(body.get("alias") or ""),
                                        str(body.get("expansion") or ""),
                                        body.get("note"))
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        repo.close()


@router.delete("/search-aliases/{alias}")
def delete_search_alias(alias: str):
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        return {"ok": repo.delete_search_alias(alias)}
    finally:
        repo.close()
