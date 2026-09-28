# -*- coding: utf-8 -*-
"""员工 Skill/工作流绑定归位（2026-09-13）：workflow 类型 key 只住 workflows 数组。

存量症状：需求分析(type=workflow) 被绑在 skills 数组 → 员工页 Skill 下拉匹配不到
选项 → 前端显示裸 key「requirement_analysis」。保存路径已自动归位，这里锁契约。
"""
from app.api.ai_colleagues import _reclassify_skill_bindings

CATALOG = {
    "requirement_analysis": {"key": "requirement_analysis", "name": "需求分析", "type": "workflow"},
    "trend_analysis": {"key": "trend_analysis", "name": "趋势分析", "type": "workflow"},
    "price_lookup": {"key": "price_lookup", "name": "查价", "type": "skill"},
}


def test_workflow_key_in_skills_moves_to_workflows():
    c = _reclassify_skill_bindings(
        {"skills": ["requirement_analysis"], "workflows": []}, CATALOG)
    assert c["skills"] == [] and c["workflows"] == ["requirement_analysis"]


def test_skill_key_stays_in_skills():
    c = _reclassify_skill_bindings(
        {"skills": ["price_lookup"], "workflows": ["trend_analysis"]}, CATALOG)
    assert c["skills"] == ["price_lookup"] and c["workflows"] == ["trend_analysis"]


def test_unknown_key_keeps_original_field():
    c = _reclassify_skill_bindings(
        {"skills": ["not_in_catalog"], "workflows": []}, CATALOG)
    assert c["skills"] == ["not_in_catalog"] and c["workflows"] == []


def test_dict_ref_with_overrides_moves_and_survives():
    c = _reclassify_skill_bindings(
        {"skills": [{"key": "trend_analysis", "enabled": False}], "workflows": []}, CATALOG)
    assert c["skills"] == [] and c["workflows"] == [{"key": "trend_analysis", "enabled": False}]


def test_duplicate_across_arrays_kept_once_in_right_bucket():
    c = _reclassify_skill_bindings(
        {"skills": ["requirement_analysis"], "workflows": ["requirement_analysis"]}, CATALOG)
    assert c["skills"] == [] and c["workflows"] == ["requirement_analysis"]
