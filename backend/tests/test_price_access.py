# -*- coding: utf-8 -*-
"""价格权限（colleague.price_access）门控测试。

定调：价格机密，AI 角色默认无价权；关闭角色的全部工具/提示词/引擎产物不得出现价格。
"""
from app.services import skill_chat
from app.services import skill_tool_context
from app.services import skill_tools_fill
from app.services import skill_tools_misc
from app.services.skill_tool_context import TOOL_CTX
from app.services.skill_tools_fill import requirement_prompt
from app.services.skill_tools_misc import tool_catalog_search
from app.services.skill_phases import catalog_models_option_data, model_option_desc


def _types_available() -> list[str]:
    from app.repository.server_catalog_repo import ServerCatalogRepository
    return [str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types() if t.get("name")]


def _with_tool_ctx(price_ok: bool):
    TOOL_CTX.set({"ext": {}, "price_ok": price_ok})


# ── 工具层：catalog_search 价格剥离 ─────────────────────────────────────

def test_catalog_search_strips_price_without_access():
    types = _types_available()
    if not types:
        return  # 空目录环境跳过
    _with_tool_ctx(price_ok=False)
    res = tool_catalog_search({"kind": "models", "type_name": types[0], "limit": 3})
    assert res.get("ok"), res
    for model in res.get("models") or []:
        assert "price" not in model, f"无价权角色拿到了价格: {model}"


def test_catalog_search_keeps_price_with_access():
    types = _types_available()
    if not types:
        return
    _with_tool_ctx(price_ok=True)
    res = tool_catalog_search({"kind": "models", "type_name": types[0], "limit": 3})
    assert res.get("ok"), res
    models = res.get("models") or []
    if models:
        assert "price" in models[0], "有价权角色应能拿到价格字段"


# ── 提示词层：禁价规则 ──────────────────────────────────────────────────

def test_requirement_prompt_carries_price_fact_not_the_rule():
    """价格纪律住在左栏（任务规则 20，由 test_constitution 的搬迁锚点守卫）。

    代码里只许出现**事实**：本角色无价格查看权限（price_access=false）。
    具体话术（禁价格数字、问价引导）是提示词，写回代码就是第二套提示词。
    """
    prompt = requirement_prompt({}, price_ok=False)
    assert "price_access=false" in prompt
    assert "禁止" not in prompt and "引导" not in prompt


def test_requirement_prompt_omits_price_fact_with_access():
    prompt = requirement_prompt({}, price_ok=True)
    assert "price_access" not in prompt


# ── 引擎层：机型选项/描述价格门控（label=机型名，desc=形态/系列/价格）────────

_CANDIDATE = {"name": "ES22V3-P", "form": "2U", "series": "Orion", "total_price": 11536.83}


def test_model_option_desc_without_price():
    desc = model_option_desc(_CANDIDATE, include_price=False)
    assert "¥" not in desc and "11,536" not in desc
    assert "2U" in desc and "Orion" in desc


def test_model_option_desc_with_price():
    desc = model_option_desc(_CANDIDATE, include_price=True)
    assert "¥" in desc and "11,537" in desc  # :,.0f 四舍五入


def test_catalog_models_option_data_price_gate():
    opts = catalog_models_option_data([_CANDIDATE], include_price=False)
    assert opts and opts[0]["label"] == "ES22V3-P" and "¥" not in opts[0]["desc"]
    opts = catalog_models_option_data([_CANDIDATE], include_price=True)
    assert opts and "¥11,537" in opts[0]["desc"]


# ── 缺省安全：未显式设置的入口（试运行等）默认可见价格，但角色链路显式传入 ──

def test_default_is_visible_for_engine_entry():
    # 引擎入口（试运行/Studio）不设 price_access 时默认 True，不影响管理员工作流
    desc = model_option_desc(_CANDIDATE)  # 默认 include_price=True
    assert "¥" in desc


def test_price_ok_default_in_tool_ctx():
    # 工具上下文未设置 price_ok 时默认可见（与引擎默认一致）
    TOOL_CTX.set({"ext": {}})
    types = _types_available()
    if not types:
        return
    res = tool_catalog_search({"kind": "models", "type_name": types[0], "limit": 1})
    models = res.get("models") or []
    if models:
        assert "price" in models[0]
