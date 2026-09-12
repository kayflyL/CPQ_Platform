# -*- coding: utf-8 -*-
"""提示词唯一出处守卫（2026-09-11 合规整改的报警器）。

宪法（docs/skill studio设计思路.md 第 1 行）：唯一 AI 大脑；拒绝硬编码；前端可配置。
所以提示词只能住在 Skill Studio 左栏（flow.graph.manual_rules + rules.reasoning_node_default
的 description / goal）。这四条断言就是「代码里又冒出第二套」的报警器：

1. 代码里不许再有 AGENT_PROTOCOL 之类注入式「系统协议」常量；
2. 空库播种契约只留结构，description / goal / prompt 一律为空；
3. 运行时节点使命**只从 DB 读**（抽屉 > DB 默认契约 > 空串），代码不编文案；
4. 没有任何脚本/代码把提示词反向写回 DB（那是平行第二套的实证）。
"""
import pathlib
import re

from app.services import skill_config_bootstrap
from app.services.skill_step_runtime import node_mission
from app.services.skill_tool_context import TOOL_CTX

BACKEND = pathlib.Path(skill_config_bootstrap.__file__).resolve().parents[2]
APP = BACKEND / "app"

_PROMPT_KEYS = {"description", "goal", "prompt", "system_prompt", "mission", "instruction"}


def _py_files(root: pathlib.Path):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_injected_protocol_constants_in_code():
    """AGENT_PROTOCOL 那类「机制约定写成系统提示词」的常量不许复活。"""
    pat = re.compile(r"^[A-Z][A-Z0-9_]*PROTOCOL[A-Z0-9_]*\s*(?::[^=]+)?=", re.M)
    hits = []
    for p in _py_files(APP):
        src = p.read_text(encoding="utf-8")
        hits += [f"{p.name}::{m.group(0).strip()}" for m in pat.finditer(src)]
    assert not hits, "代码里又出现协议常量（提示词唯一出处是左栏）：" + repr(hits)
    from app.services import skill_plan_runtime
    assert not hasattr(skill_plan_runtime, "AGENT_PROTOCOL")


def test_db_seed_contract_carries_structure_only():
    """空库播种 = 结构（产物槽/开关/数据源），不是一份藏起来的提示词。"""
    for node_key, cfg in skill_config_bootstrap.DEFAULT_REASONING_NODE_CONTRACT.items():
        leaked = sorted(k for k in cfg if k in _PROMPT_KEYS)
        assert not leaked, f"播种契约 {node_key} 又带上提示词键：{leaked}"


def test_node_mission_reads_db_only_and_stays_overridable():
    """节点使命：抽屉配置 > DB 默认契约 > 空串（不编造）。"""
    from app.services.reasoning_node_contract import node_defaults
    db = node_defaults().get("kp_reason") or {}
    db_desc = str(db.get("description") or "").strip()
    assert db_desc, "DB 里 kp_reason 使命为空，左栏提示词丢了"
    assert db_desc in node_mission("kp_reason", {})
    assert "抽屉原话" in node_mission("kp_reason", {"description": "抽屉原话"})
    assert node_mission("no_such_node", {}) == ""


def test_no_reverse_writer_pushes_prompt_text_into_db():
    """没有脚本/代码把提示词从代码常量 UPDATE 回 reasoning_node_default。"""
    assert not (BACKEND / "scripts" / "migrate_kp_reason_prompt_sync.py").exists(), \
        "反向写库脚本复活（会把左栏编辑覆盖掉）"
    hits = []
    for p in _py_files(BACKEND / "scripts") + _py_files(APP):
        if p.name == pathlib.Path(__file__).name:
            continue
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"UPDATE\s+rules\.reasoning_node_default[^\"']*", src, re.I):
            stmt = m.group(0)
            if any(k in stmt.lower() for k in ("description", "goal", "prompt")):
                hits.append(f"{p.name}::{stmt[:60]}")
    assert not hits, "有人从代码反向写提示词进 DB：" + repr(hits)


def test_live_system_prompt_is_built_from_db_text():
    """活证明：编排壳交给大脑的 system prompt 里，节点使命逐字来自 DB（左栏），无隐藏协议。"""
    from app.services import skill_turn_engine
    from app.services.reasoning_node_contract import node_defaults
    db_desc = str((node_defaults().get("kp_reason") or {}).get("description") or "").strip()
    rt = skill_turn_engine._SkillTurnRuntime(
        thread_id="t_prompt", role_key="tech", persona="你是测试同事", full_text="需要一台服务器",
        history=[], ext={}, mem={}, flow={})
    rt.engine = {"steps_done": set(), "node_labels": {}}
    rt.flow_configs = {"kp_reason": {}}
    rt.steps = [{"step": "kp_reason", "label": "配件选型"}]
    rt.manual_rules = ""
    rt._cur_step = {"key": "kp_reason", "label": "配件选型"}
    TOOL_CTX.set({"ext": {}, "engine": rt.engine})
    try:
        _user_msg, kwargs = rt._build_step_call("kp_reason", {}, {})
    finally:
        TOOL_CTX.set({})
    sys_prompt = kwargs["system_prompt"]
    assert db_desc in sys_prompt, "节点使命没从 DB 注入（提示词第二套回来了？）"
    for marker in ("系统协议", "AGENT_PROTOCOL"):
        assert marker not in sys_prompt, f"system prompt 里又夹了代码常量：{marker}"
