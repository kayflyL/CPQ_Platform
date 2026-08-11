# -*- coding: utf-8 -*-
"""list_parts 按首次报价日期(入库时间)排序单测。

入库时间排序用 MIN(kp_price_history.price_date) 作依据（见 kp_repo.list_parts 的
first_price_date 分支），而非 kp_parts.created_at——后者实测 68% 挤在一次批量导入里
没区分度。这里连真实库验证返回顺序与每件 MIN(price_date) 一致。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_kp_list_sort.py -q
"""
from sqlalchemy import func

from app.models.kp import KPPriceHistory
from app.repository.kp_repo import KPRepository


def _first_price_dates(repo, part_ids):
    """独立查每个 part 的 MIN(price_date)，核对 list_parts 排序结果用。"""
    rows = repo.session.query(KPPriceHistory.part_id, func.min(KPPriceHistory.price_date))\
        .filter(KPPriceHistory.part_id.in_(part_ids))\
        .group_by(KPPriceHistory.part_id).all()
    return {pid: d for pid, d in rows}


def test_real_db_first_price_date_desc():
    repo = KPRepository()
    try:
        res = repo.list_parts(sort_by="first_price_date", sort_order="desc",
                              page=1, page_size=30)
        items = res["items"]
        assert items, "KP 库应有配件数据"
        first_dates = _first_price_dates(repo, [it["id"] for it in items])
    finally:
        repo.close()
    seq = [first_dates[it["id"]] for it in items]
    clean = [d for d in seq if d is not None]
    assert clean == sorted(clean, reverse=True), f"未按首次报价日期降序: {seq}"


def test_real_db_first_price_date_asc():
    repo = KPRepository()
    try:
        res = repo.list_parts(sort_by="first_price_date", sort_order="asc",
                              page=1, page_size=30)
        items = res["items"]
        assert items, "KP 库应有配件数据"
        first_dates = _first_price_dates(repo, [it["id"] for it in items])
    finally:
        repo.close()
    seq = [first_dates[it["id"]] for it in items]
    clean = [d for d in seq if d is not None]
    assert clean == sorted(clean), f"未按首次报价日期升序: {seq}"
