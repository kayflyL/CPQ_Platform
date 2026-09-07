# -*- coding: utf-8 -*-
"""select_models 严格匹配单测：引擎只按信号条件精确查候选，放宽交由调用方/AI 角色，
不自动逐级放宽；无信号默认返空（空数据交角色反问）。

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
    return patch("app.services.model_candidates.ServerCatalogRepository", _Cat), \
           patch("app.services.model_candidates.BaseConfigRepository", _Bc)


def _select(series=None, no_signal_strategy=None, type_name="AI / 加速计算服务器"):
    from app.services.model_candidates import select_models
    def lm(type_id=None, series=None, form=None):
        if series == "Intel":
            return []
        return [MODEL]
    with _fake_repos(lm)[0], _fake_repos(lm)[1]:
        return select_models(None, type_name, series=series, form=None,
                             no_signal_strategy=no_signal_strategy)


def test_exact_match_returns_candidate():
    """严格命中（系列=Orion）→ 返回候选，标注精确匹配。"""
    bl = _select(series="Orion")
    assert len(bl) == 1
    assert bl[0]["match_stage"] == "exact"
    assert bl[0]["fallback_note"] == "精确匹配"


def test_mismatch_series_returns_empty_no_auto_relax():
    """库内无 Intel 平台 AI 机型 → 返空，引擎不自动放宽到其他系列（交给 AI/角色决策）。"""
    assert _select(series="Intel") == []


def test_no_signal_returns_empty():
    """无类型/系列/形态信号且未配置 fallback_all → 返空（交 clarity_check 反问）。"""
    assert _select(type_name=None) == []


def test_no_signal_fallback_all_queries_all():
    """no_signal_strategy=fallback_all → 无信号也按全量候选给 AI（专用 AI 接地路径）。"""
    bl = _select(type_name=None, no_signal_strategy="fallback_all")
    assert len(bl) == 1


def test_type_mismatch_returns_empty_not_other_type():
    """某类型 0 机型时返空反问，不丢弃 type 混入其他类型。"""
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

    with patch("app.services.model_candidates.ServerCatalogRepository", _Cat), \
         patch("app.services.model_candidates.BaseConfigRepository", _Bc):
        from app.services.model_candidates import select_models
        bl = select_models(None, "存储服务器", series="Orion", form="4U")
    assert bl == []
