# -*- coding: utf-8 -*-
"""select_models 多级放宽（fallback_order）单测：严格条件无机型时按配置逐级放宽 + 白盒说明。

全 mock（不碰 DB），可 pytest 跑。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import patch

MODEL = {
    "id": 1, "name": "ESA24V3-P", "base_config_id": 100,
    "server_type_id": 1, "use": "AI", "product_content": "x",
}
BC = {"id": 100, "model_id": 1, "series": "Orion", "form": "4U",
      "bays": 8, "parts_count": 10, "total_price": 100000.0, "bom_template_id": 7}


def _fake_repos(list_models_fn):
    """patch ServerCatalogRepository / BaseConfigRepository，list_models 行为由用例注入。"""
    class _Cat:
        def list_types(self):
            return [{"id": 1, "name": "AI / 加速计算服务器"}]
        def list_models(self, type_id=None, series=None, form=None, published_only=False):
            return list_models_fn(type_id=type_id, series=series, form=form)
        def close(self):
            pass
    class _Bc:
        def list(self):
            return [BC]
        def close(self):
            pass
    return patch("app.api.candidate_search.ServerCatalogRepository", _Cat), \
           patch("app.api.candidate_search.BaseConfigRepository", _Bc)


def _select(series="Intel", fallback_order=None):
    from app.api.candidate_search import select_models
    req_series = series
    def lm(type_id=None, series=None, form=None):
        # 只有 Orion 系列有 AI 机型；Intel 无
        if series == "Intel":
            return []
        return [MODEL]
    with _fake_repos(lm)[0], _fake_repos(lm)[1]:
        return select_models(None, "AI / 加速计算服务器", series=req_series, form=None,
                             fallback_order=fallback_order or ["exact", "same_series", "same_form", "all"])


def test_exact_match_stage():
    """严格命中（系列=Orion 有货）→ match_stage=exact，note=精确匹配。"""
    bl = _select(series="Orion")
    assert len(bl) == 1
    assert bl[0]["match_stage"] == "exact"
    assert bl[0]["fallback_note"] == "精确匹配"


def test_series_mismatch_relaxes_with_note():
    """库内无 Intel 平台 AI 机型 → 逐级放宽到同类型（same_form 命中），白盒标注放宽了平台系列。"""
    bl = _select(series="Intel")
    assert len(bl) == 1
    assert bl[0]["match_stage"] == "same_form"      # exact/same_series 都空，same_form(去系列) 命中
    assert "平台系列" in bl[0]["fallback_note"]       # 数据驱动：说明放宽了平台系列


def test_strict_no_fallback_returns_empty():
    """fallback_order 只配 exact → 严格匹配，无 Intel 机型返空（不擅自替换）。"""
    bl = _select(series="Intel", fallback_order=["exact"])
    assert bl == []


def test_all_stage_drops_series_and_form():
    """fallback_order 只含 all → 直接从只保类型开始，命中且标注放宽。"""
    bl = _select(series="Intel", fallback_order=["all"])
    assert len(bl) == 1
    assert bl[0]["match_stage"] == "all"
    assert "平台系列" in bl[0]["fallback_note"]


def test_type_mismatch_returns_empty_not_other_type():
    """某类型 0 机型时返空反问，不丢弃 type 混入其他类型（N3 回归）。"""
    def lm(type_id=None, series=None, form=None):
        if type_id == 1:
            return []
        return [MODEL]

    class _Cat:
        def list_types(self):
            return [{"id": 1, "name": "存储服务器"}, {"id": 2, "name": "AI / 加速计算服务器"}]

        def list_models(self, type_id=None, series=None, form=None, published_only=False):
            return lm(type_id=type_id, series=series, form=form)

        def close(self):
            pass

    class _Bc:
        def list(self):
            return [BC]

        def close(self):
            pass

    with patch("app.api.candidate_search.ServerCatalogRepository", _Cat), \
         patch("app.api.candidate_search.BaseConfigRepository", _Bc):
        from app.api.candidate_search import select_models
        bl = select_models(None, "存储服务器", series="Orion", form="4U",
                           fallback_order=["exact", "same_series", "same_form", "all"])
    assert bl == []
