# -*- coding: utf-8 -*-
"""llm_ask 反问目录锚定（B 方案）单测：选项白名单过滤（禁塔式）/ 空选项兜底 / 形态白名单从目录派生。

纯函数 + mock LLM（不碰真 LLM）；_catalog_whitelist 用固定白名单注入。
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

from unittest.mock import patch

from app.services import capabilities as cap


def _whitelist():
    return {
        "types": ["通用计算服务器", "AI / 加速计算服务器", "存储服务器"],
        "series": ["Orion", "Polaris"],
        "forms": ["1U", "2U", "4U"],
        "models": ["ES22V3-P", "ESA24V3-P"],
    }


# ── _filter_catalog_options ──────────────────────────────────────────

def test_filter_drops_tower_keeps_valid():
    """塔式/卧式/刀片必须被过滤；机架式（别名）/类型/形态保留。"""
    opts = ["塔式（适合办公室环境）", "卧式", "机架式（适合机房/数据中心）", "1U", "AI / 加速计算服务器"]
    out = cap._filter_catalog_options(opts, _whitelist())
    joined = "".join(out)
    assert "塔式" not in joined and "卧式" not in joined
    assert "机架式" in joined or "1U" in joined or "AI / 加速计算服务器" in joined


def test_filter_all_invalid_returns_empty():
    """LLM 只给编造选项 → 过滤后为空（触发上层目录兜底）。"""
    out = cap._filter_catalog_options(["塔式", "刀片服务器"], _whitelist())
    assert out == []


def test_filter_keeps_delegation_option():
    """委托类选项（不确定/你推荐）放行——AI 开也保留客户把决定权交回系统的出口（与 AI 关一致）。"""
    out = cap._filter_catalog_options(["不确定，推荐机架式", "塔式"], _whitelist())
    assert out == ["不确定，推荐机架式"]


# ── _catalog_fallback_options ────────────────────────────────────────

def test_fallback_options_by_missing_field():
    """缺失项关键词 → 对应目录维度；形态缺失给形态，其余给类型。"""
    assert cap._catalog_fallback_options(["服务器形态"], _whitelist()) == ["1U", "2U", "4U"]
    assert cap._catalog_fallback_options(["服务器类型"], _whitelist()) == ["通用计算服务器", "AI / 加速计算服务器", "存储服务器"]
    assert cap._catalog_fallback_options(["系列"], _whitelist()) == ["Orion", "Polaris"]
    assert cap._catalog_fallback_options(["预算"], _whitelist()) == ["通用计算服务器", "AI / 加速计算服务器", "存储服务器"]


# ── run_llm_ask（mock LLM + 固定白名单）──────────────────────────────

async def _ask(missing=None, llm_opts=None, llm_q="您需要哪种服务器形态？", workload=False):
    cfg = {"strategy": "one"}
    if workload:
        cfg["workload_categories"] = [{"label": "AI / 机器学习", "desc": "训练/推理", "type": "AI / 加速计算服务器"}]
    ctx = {"requirement_text": "我想配一台 AI 服务器", "ext": {}, "missing_fields": missing or ["服务器形态"], "llm_enabled": True}

    async def _chat(messages, schema=None, temperature=None):
        return {"question": llm_q, "options": llm_opts or [], "why": "影响选型"}

    with patch.object(cap, "_ai_enabled", return_value=True), \
         patch.object(cap, "_catalog_whitelist", return_value=_whitelist()), \
         patch("app.services.llm_client.chat_json", _chat):
        return await cap.run_llm_ask(ctx, cfg)


def test_ask_tower_option_dropped():
    """LLM 给出塔式 → 选项里没有塔式。"""
    res = asyncio.run(_ask(missing=["服务器形态"], llm_opts=["塔式（适合办公室）", "2U 机架式"]))
    assert res["ok"] is True
    assert not any("塔式" in o for o in res["options"])


def test_ask_all_invalid_falls_back_to_catalog():
    """LLM 选项全非法 → 兜底给目录形态（非空、无塔式）。"""
    res = asyncio.run(_ask(missing=["服务器形态"], llm_opts=["塔式", "卧式"]))
    assert res["ok"] is True and res["options"]
    joined = "".join(res["options"])
    assert "塔式" not in joined and "卧式" not in joined
    assert any(f in res["options"] for f in ("1U", "2U", "4U"))


def test_ask_workload_options_kept():
    """工作负载模式：选项来自可配 workload_categories（放行，不按目录过滤）。"""
    res = asyncio.run(_ask(missing=["用途/场景"], llm_opts=["AI / 机器学习"], workload=True))
    assert res["ok"] is True
    assert "AI / 机器学习" in res["options"]


# ── _catalog_whitelist 形态派生 ──────────────────────────────────────

def test_whitelist_forms_derived_from_catalog():
    """形态白名单从目录派生：真实来源=基准配置 form（机型自身无 form 列）；去重。"""
    fake_types = [{"id": 1, "name": "通用计算服务器"}]
    fake_models = {"通用计算服务器": [
        {"id": 1, "name": "M1", "base_config": {"form": "2U"}},
        {"id": 2, "name": "M2", "base_config": {"form": "4U"}},
        {"id": 3, "name": "M3", "base_config": {"form": "2U"}},   # 去重
        {"id": 4, "name": "M4", "form": "3U"},                    # 顶层 form 兜底
    ]}
    with patch("app.services.catalog_guide.load_catalog", return_value=(fake_types, fake_models)), \
         patch("app.repository.system_config_repo.SystemConfigRepository") as _repo:
        _repo.return_value.get_value.return_value = [{"value": "Orion"}]
        _repo.return_value.close = lambda: None
        w = cap._catalog_whitelist()
    assert w["forms"] == ["2U", "4U", "3U"]     # base_config.form 优先 + 顶层 form 兜底，去重
    assert w["types"] == ["通用计算服务器"]
    assert "Orion" in w["series"]


def test_whitelist_forms_fallback_when_catalog_empty():
    """目录为空 → 形态回退常量 _FORM_WHITELIST（不崩）。"""
    with patch("app.services.catalog_guide.load_catalog", return_value=([], {})), \
         patch("app.repository.system_config_repo.SystemConfigRepository") as _repo:
        _repo.return_value.get_value.return_value = []
        _repo.return_value.close = lambda: None
        w = cap._catalog_whitelist()
    assert w["forms"] == list(cap._FORM_WHITELIST)


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  ✅ {fn.__name__}"); passed += 1
        except Exception:
            print(f"  ❌ {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
