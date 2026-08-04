# -*- coding: utf-8 -*-
"""LLM 主理解节点 llm_understand：prompt / 语义校验重试 / 降级 / 合并。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_llm_understand.py -q
"""
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from app.services import llm_client
from app.services.llm_understand import build_messages, run_llm_understand
from app.services.reasoning_executor import _dispatch

CATALOG = {
    "server_types": ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"],
    "models_by_type": {"AI / 加速计算服务器": ["ESA 4U-8卡", "ZSA 2U-8卡"]},
    "series": ["Orion", "Polaris", "Intel", "工作站"],
    "forms": ["1U", "2U", "4U", "5U", "6U", "8U"],
    "family_words": {"CPU": ["epyc", "xeon", "kh50000"], "GPU": ["h100", "a100", "rtx"]},
    "slots_spec": [{"key": "series", "label": "所属系列", "level": "L0"},
                   {"key": "form", "label": "机箱形态", "level": "L1"}],
}

VALID_DATA = {
    "series": {"value": "Orion", "confidence": 0.9, "source": "text", "evidence": "需求提到 AMD"},
    "form": {"value": "2U", "confidence": 0.8, "source": "text", "evidence": "需求提到 2U"},
    "cpu": {"model": "EPYC 9254", "qty": 2, "confidence": 0.7, "source": "infer", "evidence": "需求提到两颗 EPYC"},
    "intent_summary": "AI 训练服务器",
    "missing": ["网卡"],
    "questions": ["需要几块网卡？"],
}


def _patch_env(chat_return=None, chat_side=None, llm_enabled=True):
    m = AsyncMock(return_value=chat_return)
    if chat_side is not None:
        m.side_effect = chat_side
    patches = [
        patch("app.services.llm_client.chat_json", m),
        patch("app.services.llm_client.is_llm_enabled", return_value=llm_enabled),
        patch("app.services.llm_understand.build_catalog_context", return_value=CATALOG),
        patch("app.services.requirement_intel_service._load_series_values",
              return_value=["Orion", "Polaris", "Intel", "工作站"]),
    ]
    return patches, m


def _use(patches):
    es = ExitStack()
    for p in patches:
        es.enter_context(p)
    return es


def _run(text, ext, config):
    return asyncio.run(run_llm_understand(text, ext, config))


# ============================================================
# build_messages —— 需求 + 规则摘要 + 目录白名单 + 校验反馈
# ============================================================

def test_build_messages_contains_requirement_and_catalog():
    msgs = build_messages("两台 AMD 2U 服务器", {"series": "Orion"}, CATALOG)
    user = msgs[1]["content"]
    assert "需求原文" in user and "两台 AMD 2U 服务器" in user
    assert "在售目录白名单" in user
    assert "AI / 加速计算服务器" in user
    assert "Orion" in user
    assert msgs[0]["role"] == "system"


def test_build_messages_appends_feedback():
    msgs = build_messages("服务器", {}, CATALOG, feedback=["系列「Huawei」不在白名单"])
    user = msgs[1]["content"]
    assert "未通过校验" in user
    assert "系列「Huawei」不在白名单" in user


# ============================================================
# run_llm_understand —— 开关 / 全局关 / 成功 / 重试 / 降级
# ============================================================

def test_disabled_by_default_skips_llm():
    patches, m = _patch_env(chat_return=VALID_DATA)
    with _use(patches):
        ext = {"series": "Orion", "keywords": []}
        res = _run("两台 AMD 2U 服务器", ext, {"enable_llm": False})
    assert res["called"] is False
    assert res["reason"] == "disabled"
    m.assert_not_called()


def test_global_ai_disabled_skips_llm():
    patches, m = _patch_env(chat_return=VALID_DATA, llm_enabled=False)
    with _use(patches):
        res = _run("两台 AMD 2U 服务器", {}, {"enable_llm": True})
    assert res["called"] is False
    assert res["reason"] == "global_ai_disabled"
    m.assert_not_called()


def test_success_merges_into_ext():
    patches, m = _patch_env(chat_return=VALID_DATA)
    with _use(patches):
        ext = {"keywords": ["9254"]}
        res = _run("两台 AMD EPYC 9254 2U 服务器", ext, {"enable_llm": True})
    assert res["called"] is True
    assert res["reason"] == "ok"
    assert res["merged"] is True
    assert ext["series"] == "Orion"
    assert ext["form"] == "2U"
    assert ext["cpu_signal"]["model"] == "EPYC 9254"
    assert res["coverage"]["filled"] >= 2
    assert res["intent_summary"] == "AI 训练服务器"
    assert res["missing"] == ["网卡"]
    m.assert_called_once()


def test_validation_retry_then_success():
    bad = dict(VALID_DATA)
    bad["series"] = {"value": "Huawei", "confidence": 0.9, "source": "infer", "evidence": "x"}
    good = dict(VALID_DATA)
    patches, m = _patch_env(chat_side=[bad, good])
    with _use(patches):
        ext = {"keywords": []}
        res = _run("AMD EPYC 9254 2U", ext, {"enable_llm": True})
    assert res["called"] is True
    assert res["retried"] is True
    assert res["merged"] is True
    assert ext["series"] == "Orion"     # 重试后的正确值合并
    assert m.await_count == 2


def test_llm_error_degrades_silently():
    patches, m = _patch_env(chat_side=llm_client.LLMError("boom"))
    with _use(patches):
        ext = {"series": "Orion", "keywords": []}
        res = _run("服务器", ext, {"enable_llm": True})
    assert res["called"] is True
    assert res["reason"] == "llm_error"
    assert "boom" in (res["error"] or "")
    assert res["merged"] is False
    assert ext == {"series": "Orion", "keywords": []}   # 规则结果原样


# ============================================================
# 兜底：脏配置 / 未预期异常都不拖垮流程
# ============================================================

def test_dirty_max_retry_config_falls_back_to_1():
    patches, m = _patch_env(chat_return=VALID_DATA)
    with _use(patches):
        ext = {"keywords": []}
        res = _run("AMD EPYC 9254", ext, {"enable_llm": True, "max_retry": "abc"})
    assert res["called"] is True
    assert res["reason"] == "ok"
    assert res["merged"] is True
    m.assert_called_once()


def test_dispatch_degrades_on_unexpected_exception():
    """run_llm_understand 抛未预期异常 → 节点降级 payload（node_error），不抛给整条图。"""
    async def _boom(text, ext, config, **kwargs):
        raise RuntimeError("unexpected boom")

    async def _broadcast(_p):
        return None

    # _dispatch 内是 `from app.services.llm_understand import run_llm_understand`，需 patch 源头模块
    with patch("app.services.llm_understand.run_llm_understand", side_effect=_boom):
        payload = asyncio.run(_dispatch(
            "llm_understand",
            {"requirement_text": "服务器", "ext": {"series": "Orion"}},
            {"enable_llm": True},
            _broadcast,
        ))
    assert payload["called"] is True
    assert payload["reason"] == "node_error"
    assert "unexpected boom" in (payload["error"] or "")
    assert payload["merged"] is False
