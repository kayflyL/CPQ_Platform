# -*- coding: utf-8 -*-
"""skill 落地契约单测：grounding_envelope / validate_grounding / 工具 digest 类型可见。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _part(**kw):
    base = {
        "category": "CPU", "pn": "PN1", "name": "n", "qty": 1,
        "unmatched": False, "unmatched_reason": "",
        "spec_mismatch": False, "request_spec": "", "grounded_spec": "",
    }
    base.update(kw)
    return base


def test_grounding_envelope_partitions_parts():
    from app.services.skill_contracts import grounding_envelope
    env = grounding_envelope([
        _part(pn="A"),
        _part(pn="", unmatched=True, unmatched_reason="库无"),
        _part(pn="B", spec_mismatch=True),
        _part(pn="C", substitution={"reason": "64G×2 组 128G", "source": "compose_capacity"}),
    ])
    assert len(env["matched"]) == 2
    assert len(env["unmatched"]) == 1
    assert len(env["spec_mismatch"]) == 1
    assert len(env["substitutions"]) == 1
    assert env["count"] == 4


def test_validate_grounding_ok_and_failures():
    from app.services.skill_contracts import validate_grounding
    assert validate_grounding({
        "matched": [_part(pn="A")],
        "unmatched": [_part(pn="", unmatched=True, unmatched_reason="库无")],
        "spec_mismatch": [],
        "substitutions": [],
    }) == []
    errors = validate_grounding({
        "matched": [_part(pn="")],
        "unmatched": [_part(pn="", unmatched=True)],
        "spec_mismatch": [],
        "substitutions": [{"reason": ""}],
    })
    assert any("缺料号" in e for e in errors)
    assert any("缺原因" in e for e in errors)
    assert any("缺 reason 或 source" in e for e in errors)


def test_select_models_digest_exposes_type():
    from app.services.agent_tool_handlers import _tool_select_models
    out = asyncio.run(_tool_select_models({"server_type_name": "AI / 加速计算服务器"}))
    cands = out.get("candidates") or []
    assert cands, "AI 类型应有候选机型"
    assert all("server_type_name" in c for c in cands)
    assert all(c["server_type_name"] == "AI / 加速计算服务器" for c in cands)
