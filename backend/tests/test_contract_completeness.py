# -*- coding: utf-8 -*-
"""工作流节点契约完整性守卫（防"自创格式/目标层为空"的结构性防线）。

遍历所有 active 工作流：每个挂了工具的节点必须有 target.artifact（含 kind/slot/view），
且完成声明（completion）存在。格式不对 = CI 红——目标层格式偏差在构建期就暴露，
不等用户打开画布才发现。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.transaction_engine import load_flow_rules

REQUIRED_KINDS = {"document", "form", "table", "record"}
REQUIRED_TARGET_KEYS = {"kind", "name", "slot", "view"}


def _all_workflows():
    repo = ReasoningFlowRepository()
    try:
        rows = repo.session.execute(
            __import__("sqlalchemy").text(
                "SELECT skill_key FROM rules.reasoning_flow WHERE is_active = true AND skill_key IS NOT NULL"
            )
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        repo.close()


@pytest.mark.parametrize("skill_key", _all_workflows())
def test_workflow_node_contracts_complete(skill_key):
    rules = load_flow_rules(skill_key)
    if not rules["steps"]:
        pytest.skip(f"{skill_key}: 无挂工具节点")
    for step in rules["steps"]:
        fields = step.get("fields") or []
        # 有字段契约的节点：每个 ask=true 的字段必须有 label 和 hint
        for f in fields:
            if f.get("ask"):
                assert f.get("label"), f"{skill_key}.{step['key']}: ask 字段缺 label"
                assert f.get("hint"), f"{skill_key}.{step['key']}: ask 字段缺 hint（告诉大脑怎么问）"


def test_all_transaction_workflows_have_completion_declarations():
    """事务引擎驱动的工作流（real_bound）：每个挂工具的节点必须有 completion 声明。
    需求分析等推理管道工作流不走事务引擎，不在校验范围内。"""
    from app.services.transaction_engine import resolve_app
    repo = ReasoningFlowRepository()
    try:
        rows = repo.session.execute(
            __import__("sqlalchemy").text(
                "SELECT skill_key FROM rules.reasoning_flow WHERE is_active = true AND skill_key IS NOT NULL"
            )
        ).fetchall()
        skill_keys = [r[0] for r in rows]
    finally:
        repo.close()
    for key in skill_keys:
        from app.services.transaction_engine import resolve_app as _ra
        if _ra(key) is None:
            continue  # 非事务引擎工作流，跳过
        rules = load_flow_rules(key)
        for step in rules["steps"]:
            comp = step.get("completion")
            assert comp is not None, (
                f"{key}.{step['key']}: 缺 completion 声明——指针会卡死在此步。"
                f"请在画布节点配置中声明 completion（{{slot/flag/any_of}}）。"
            )
