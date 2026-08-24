# -*- coding: utf-8 -*-
"""kp_token_context 规则库访问单测：默认词表 + 规则覆盖合并。
跑法（backend 目录）：python -X utf8 -m pytest tests/test_kp_token_context.py -q
"""
from app.services import requirement_rule_catalog as rc


def test_defaults_present():
    ctx = rc.kp_token_context()
    assert ctx["series_words"] == ["系列", "series"]
    assert "风扇" in ctx["fan_words"]
    assert set(ctx["psu_words"]) == {"瓦", "白金", "热插拔", "电源", "psu", "redundant", "platinum"}
    assert ctx["gpu_cat_keywords"] == ["gpu", "显卡"]
    assert ctx["raid_cat_keywords"] == ["raid", "阵列"]


def test_override_merges(monkeypatch):
    monkeypatch.setattr(rc, "active_bodies", lambda *a, **k: [{"series_words": ["代"]}])
    ctx = rc.kp_token_context()
    assert ctx["series_words"] == ["代"]
    assert ctx["psu_words"] == ["瓦", "白金", "热插拔", "电源", "psu", "redundant", "platinum"]
