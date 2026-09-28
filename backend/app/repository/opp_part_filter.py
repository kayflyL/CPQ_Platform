"""报价单配件筛选：按 quotation_items 明细匹配商机。

口径：多行条件=同时满足（同一张报价单里都含）；同行多关键词=任一命中；
数量按「同一报价单 × 同一配置页签」内命中行求和判定（防两个配置各 4 卡凑 8 卡）。
红线：命中摘要只带 型号(catalogue)/数量/配置名/报价日期，不带 PN、不带价格。
"""
from typing import List, Optional

_MAX_ROWS = 6
_MAX_KEYWORDS = 6
_MAX_HITS_PER_OPP = 3
_MAX_PARTS_PER_HIT = 6


def normalize_part_filters(raw) -> List[dict]:
    """清洗前端传入的条件行 [{category, keywords[], qty_min}]，非法行丢弃。"""
    rows: List[dict] = []
    if not isinstance(raw, list):
        return rows
    for r in raw:
        if not isinstance(r, dict):
            continue
        kws = [str(k).strip() for k in (r.get("keywords") or []) if str(k).strip()][:_MAX_KEYWORDS]
        if not kws:
            continue
        cat = str(r.get("category") or "").strip()
        try:
            qty = int(r.get("qty_min") or 0)
        except (TypeError, ValueError):
            qty = 0
        rows.append({"category": cat or None, "keywords": kws, "qty_min": qty if qty > 0 else None})
    return rows[:_MAX_ROWS]


def match_opportunities_by_parts(session, opp_ids: List[str], part_rows: list,
                                 quote_start: Optional[str] = None,
                                 quote_end: Optional[str] = None) -> dict:
    """按报价明细匹配商机，返回 {opportunity_id: [hit, ...]}。

    hit = {date: 报价日期, cfg: 配置页签名, parts: [{name, qty}]}，每商机最多 3 条、日期新在前。
    quote_start/quote_end（字符串 "YYYY-MM-DD HH:MM:SS"）非空时限定报价创建时间窗口。
    """
    from app.models.quotation import Quotation
    from app.models.quotation_item import QuotationItem

    rows = normalize_part_filters(part_rows)
    out: dict = {}
    if not rows or not opp_ids:
        return out
    q_q = session.query(Quotation).filter(
        Quotation.opportunity_id.in_(opp_ids),
        Quotation.status == "active",
    )
    if quote_start:
        q_q = q_q.filter(Quotation.created_at >= quote_start)
    if quote_end:
        q_q = q_q.filter(Quotation.created_at < quote_end)
    quotations = q_q.all()
    if not quotations:
        return out
    qmap = {q.quotation_id: q for q in quotations}
    items = session.query(QuotationItem).filter(
        QuotationItem.quotation_id.in_(list(qmap.keys()))
    ).all()

    def _item_matches(item, row) -> bool:
        if row["category"]:
            if (item.part_category or "").strip().lower() != row["category"].lower():
                return False
        hay = f"{item.catalogue or ''} {item.description or ''}".lower()
        return any(k.lower() in hay for k in row["keywords"])

    groups: dict = {}
    for it in items:
        cfg = (it.config_name or "").strip()
        groups.setdefault((it.quotation_id, cfg), []).append(it)

    for (qid, cfg), gitems in groups.items():
        quo = qmap.get(qid)
        if not quo:
            continue
        agg: dict = {}
        for row in rows:
            matched = [it for it in gitems if _item_matches(it, row)]
            if not matched:
                break
            if row["qty_min"] and sum(int(it.qty or 0) for it in matched) < row["qty_min"]:
                break
            for it in matched:
                name = (it.catalogue or it.description or "").strip()
                if name:
                    agg[name] = agg.get(name, 0) + int(it.qty or 0)
        else:
            parts = [{"name": n, "qty": q} for n, q in agg.items()][:_MAX_PARTS_PER_HIT]
            if not parts:
                continue
            out.setdefault(quo.opportunity_id, []).append(
                {"date": str(quo.created_at or "")[:10], "cfg": cfg, "parts": parts}
            )

    for oid in out:
        out[oid].sort(key=lambda h: h["date"], reverse=True)
        out[oid] = out[oid][:_MAX_HITS_PER_OPP]
    return out
