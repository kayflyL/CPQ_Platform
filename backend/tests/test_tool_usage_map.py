# -*- coding: utf-8 -*-
"""工具目录「被引用」映射（compute_tool_usage）：聚合口径必须与运行时一致——
默认契约 + 增量 + 机制保底（effective_node_tools），标签取 capability_spec。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.repository import reasoning_flow_repo as rfr


@pytest.fixture(autouse=True)
def _pure_defaults(monkeypatch):
    """默认契约不走 DB：本测试只考聚合逻辑本身。"""
    defaults = {
        "agent_fill": {"enabled_tools": []},
        "model_reason": {"enabled_tools": ["choose_model"]},
        "kp_reason": {"enabled_tools": ["query_parts", "select_parts", "ask_user", "inspect_parts"]},
    }
    monkeypatch.setattr(rfr, "_node_defaults_for", lambda skill_key: defaults)


def test_mechanism_tools_counted_even_with_empty_config():
    """增量/默认全空 → 机制保底照常计入（与运行时同一口径）。"""
    snap = {"skill_key": "requirement_analysis",
            "graph": {"nodes": [{"id": "kp_reason", "type": "kp_reason", "label": "配件选型"}]},
            "node_deltas": {}}
    usage = rfr.compute_tool_usage([snap])
    assert set(usage["query_parts"]) == {"配件选型"}
    assert set(usage["select_parts"]) == {"配件选型"}
    assert set(usage["ask_user"]) == {"配件选型"}
    assert set(usage["inspect_parts"]) == {"配件选型"}


def test_delta_enhancement_counted_and_deduped_across_flows():
    """增量挂上的增强工具计入；两条流同名节点去重成一个标签。"""
    snaps = [
        {"skill_key": "requirement_analysis",
         "graph": {"nodes": [{"id": "agent_fill", "type": "agent_fill", "label": "智能对话填表 Agent"}]},
         "node_deltas": {"agent_fill": {"enabled_tools": ["catalog_search"]}}},
        {"skill_key": "trend_analysis",
         "graph": {"nodes": [{"id": "agent_fill", "type": "agent_fill", "label": "智能对话填表 Agent"}]},
         "node_deltas": {"agent_fill": {"enabled_tools": ["search_cases"]}}},
    ]
    usage = rfr.compute_tool_usage(snaps)
    assert set(usage["catalog_search"]) == {"智能对话填表 Agent"}
    assert set(usage["search_cases"]) == {"智能对话填表 Agent"}
    assert set(usage["fill_requirement"]) == {"智能对话填表 Agent"}  # 机制保底


def test_suffixed_and_unknown_nodes_fall_back_to_labels():
    """画布复制出的后缀节点（agent_fill_2）回基础类型取标签；未知类型用图内 label。"""
    snap = {"skill_key": "requirement_analysis",
            "graph": {"nodes": [
                {"id": "agent_fill_2", "type": "agent_fill", "label": "副本"},
                {"id": "custom_x", "type": "custom", "label": "自定义节点"},
            ]},
            "node_deltas": {"agent_fill_2": {"enabled_tools": ["query_data"]},
                            "custom_x": {"enabled_tools": ["query_data"]}}}
    usage = rfr.compute_tool_usage([snap])
    assert set(usage["query_data"]) == {"智能对话填表 Agent", "自定义节点"}
    assert "custom_x" not in usage
