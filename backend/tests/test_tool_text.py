# -*- coding: utf-8 -*-
"""工具文案三层拆分（2026-09-15 A1+A2）：
  - 人类层默认值来自 agent_tool_display（display_name/one_liner/人话 description）
  - DB 覆盖层（agent_tool_text）盖在默认之上：model_brief 覆盖 = 模型 FC 契约被替换
  - 宪法 lint（find_prose_markers）与 test_constitution 共用同一词表
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import agent_tool_specs as ats
from app.services.agent_tool_display import TOOL_DISPLAY
from app.services.constitution_lint import find_prose_markers


def test_prose_lint_hits_and_clean():
    assert "先调" in find_prose_markers("必须先调 query_parts 再锁定")
    assert "建议" in find_prose_markers("建议向客户确认")
    assert find_prose_markers("") == []
    assert find_prose_markers(None) == []
    # 契约句（事实/参数描述）不命中
    assert find_prose_markers("model 只能取候选池内的值；池外取值一律拒绝") == []
    assert find_prose_markers("行类目（如 Memory/NIC/CPU）") == []


def test_catalog_defaults_human_layer(monkeypatch):
    monkeypatch.setattr(ats, "_tool_text_overrides", lambda: {})
    catalog = {t["name"]: t for t in ats.tool_catalog()}
    assert set(catalog) == set(TOOL_DISPLAY)  # 9 个工具都有人类层文案
    for name, entry in catalog.items():
        assert entry["display_name"], name
        assert entry["one_liner"], name
        assert entry["description"], name
        assert entry["custom"] == []
        # 无覆盖时模型契约 = 代码 summary
        assert entry["summary"] == ats._TOOL_SPECS[name].get("summary")


def test_catalog_and_registry_consume_overrides(monkeypatch):
    monkeypatch.setattr(ats, "_tool_text_overrides",
                        lambda: {"query_parts": {"display_name": "配件搜索(自定义)",
                                                 "model_brief": "自定义模型契约文本。"}})
    catalog = {t["name"]: t for t in ats.tool_catalog()}
    entry = catalog["query_parts"]
    assert entry["display_name"] == "配件搜索(自定义)"
    assert entry["summary"] == "自定义模型契约文本。"
    assert set(entry["custom"]) == {"display_name", "model_brief"}
    # 未被覆盖的工具不受影响
    assert catalog["ask_user"]["custom"] == []

    # 注册表（模型真实吃到的 FC schema）吃到同一覆盖
    reg = ats.build_tool_registry({"enabled_tools": ["query_parts"]})
    schema = next(s for s in reg.schemas() if s["function"]["name"] == "query_parts")
    assert schema["function"]["description"] == "自定义模型契约文本。"
