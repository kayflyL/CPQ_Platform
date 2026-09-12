# -*- coding: utf-8 -*-
"""拆分布局守卫（2026-09-10 文件级 + 函数级拆分之后）。

1. 谁在哪：拆出的模块必须真在自己的文件里（不许回锅进 skill_chat）；
2. 多大：两个原怪物函数只剩薄封装，运行时类的阶段方法各有预算；
3. 死代码：清掉的零引用名字不许复活。

拆分不难，难的是不长回去——这些断言就是「又长回去了」的报警器。
"""
import ast
import importlib
import inspect
import pathlib

from app.services import skill_chat, skill_turn_engine

OWNERS = {
    "skill_tool_context": ["TOOL_CTX"],
    "skill_memory": ["_load_mem", "_save_mem", "_slots_view", "_kp_status_rows", "_brain_note_summary"],
    "skill_signals": ["_match_card_signal", "_signal_with_qty", "_apply_registration_signal",
                      "_brain_ask_manual_signal", "_manual_model_signal"],
    "skill_step_runtime": ["_engine_begin_step", "_node_done_payload",
                           "_emit_step_trace", "_emit_brain_status"],
    "skill_tools_fill": ["requirement_prompt", "_normalize_fill_keys", "tool_fill_requirement",
                         "fill_tool_parameters", "_fill_contract_brief"],
    "skill_tools_model": ["tool_select_model"],
    "skill_tools_kp": ["_zero_reason", "_search_kp_parts_by_rows",
                       "tool_query_parts"],
    "skill_tools_open": ["_brief_specs", "_spec_profile",
                         "_grep_hit", "_snippet", "tool_open_part", "tool_open_row",
                         "tool_open_category", "tool_grep_parts", "tool_inspect_parts"],
    "skill_tools_select": ["tool_select_parts"],
    "skill_tools_misc": ["tool_catalog_search", "tool_query_data", "tool_ask_user"],
    "skill_turn_engine": ["run_skill_agent_turn", "run_brain_attempts", "step_gate_verdict",
                          "_merged_narration"],
    # part_selector 拆分（2026-09-11）：行身份 / 检索召回 / 落料 三块 + 底层规格事实，
    # 原文件退化成总出口薄壳（实现回锅由 test_part_selector_stays_a_thin_facade 挡）。
    "part_specs": ["_gb_of", "_series_ok", "_SeriesScopedRepo", "_spec_hit", "kp_repository"],
    "part_row_identity": ["kp_row_key", "row_ref_meta", "kp_row_id", "kp_row_id",
                          "stamp_row_identity", "row_content_rev", "pick_for_row",
                          "apply_kp_picks", "apply_kp_waived", "resolve_row_ref"],
    "part_recall": ["kp_candidate_pools", "resolve_kp_pools", "retrieve_part_candidates",
                    "list_kp_categories", "resolve_kp_category", "resolve_part_alias",
                    "CANDIDATE_RESOLVERS"],
    "part_landing": ["select_parts", "manual_pick_options", "manual_signal_for_text",
                     "_ground_cpu", "_ground_memory", "_ground_storage", "_ground_gpu",
                     "_ground_raid", "_ground_nic", "_ground_generic"],
}

# 配件层分块：依赖只能向下（specs ← identity ← recall ← landing），单文件不许再长回一头。
PART_LAYERS = ["part_specs", "part_row_identity", "part_recall", "part_landing"]
PART_LINE_BUDGET = 700


def test_each_split_module_owns_its_names():
    """拆出的名字必须住在归属模块里（改名搬家要同步这里的归属表）。"""
    missing = []
    for mod_name, names in OWNERS.items():
        mod = importlib.import_module("app.services." + mod_name)
        missing += [f"{mod_name}::{n}" for n in names if not hasattr(mod, n)]
    assert not missing, "拆出的名字不在归属模块里：" + repr(missing)


def test_entrypoints_stay_thin():
    """两个入口只剩薄封装（原为 451 / 586 行的两个怪物函数）。"""
    for fn in (skill_chat.handle_skill_chat_turn, skill_turn_engine.run_skill_agent_turn):
        size = len(inspect.getsource(fn).splitlines())
        assert size <= 40, f"{fn.__name__} 又长回 {size} 行（应为薄封装）"


def test_runtime_classes_keep_their_phases():
    """回合运行时类：阶段方法在，主 run 只做顺序编排。"""
    want = {
        skill_chat._ChatTurnRuntime: ["_prepare", "_apply_card_selections", "_chat_phase",
                                      "_run_task", "_emit_ask_card", "_emit_done", "_emit_gaps", "run"],
        skill_turn_engine._SkillTurnRuntime: ["_prepare", "_emit_pipeline_start", "_build_step_call",
                                              "_settle", "_run_one_step", "_deliver", "run"],
    }
    for cls, names in want.items():
        absent = [n for n in names if not callable(getattr(cls, n, None))]
        assert not absent, f"{cls.__name__} 缺阶段方法：{absent}"
        size = len(inspect.getsource(cls.run).splitlines())
        assert size <= 45, f"{cls.__name__}.run 不再是纯编排（{size} 行）"


def test_no_method_exceeds_the_line_budget():
    """单个方法的行数预算 120（拆分前两个怪物分别是 451 / 586 行）。"""
    over = []
    for cls in (skill_chat._ChatTurnRuntime, skill_turn_engine._SkillTurnRuntime):
        for name, fn in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith("__"):
                continue
            size = len(inspect.getsource(fn).splitlines())
            if size > 120:
                over.append(f"{cls.__name__}.{name}={size}")
    assert not over, "方法超出 120 行预算：" + repr(over)


def test_dead_names_stay_dead():
    """清掉的零引用名字不许复活（拆分管线里删的 3 个死代码）。"""
    root = pathlib.Path(skill_chat.__file__).parent
    dead = ("_kp_pending_rows", "clear_memory", "_index_bucket_rows")
    hits = []
    for p in root.glob("skill_*.py"):
        src = p.read_text(encoding="utf-8")
        hits += [f"{p.name}::{d}" for d in dead if d in src]
    assert not hits, "死代码复活：" + repr(hits)


def test_part_selector_stays_a_thin_facade():
    """part_selector 只能是总出口：实现住在四个语义模块里，不许在壳里回锅。"""
    from app.services import part_selector
    src = pathlib.Path(part_selector.__file__).read_text(encoding="utf-8")
    defs = [n.name for n in ast.parse(src).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    assert not defs, "part_selector 又长出实现（应搬到语义模块）：" + repr(defs)


def test_part_modules_stay_layered():
    """配件层依赖只能向下（specs ← identity ← recall ← landing）：不许反向或成环。"""
    idx = {m: i for i, m in enumerate(PART_LAYERS)}
    bad = []
    for m in PART_LAYERS:
        src = pathlib.Path(importlib.import_module("app.services." + m).__file__).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                dep = (node.module or "").rsplit(".", 1)[-1]
                if dep in idx and idx[dep] >= idx[m]:
                    bad.append(f"{m}->{dep}")
    assert not bad, "配件层出现反向/同层依赖：" + repr(sorted(set(bad)))


def test_part_modules_stay_within_line_budget():
    """拆完别再长回去：每个语义模块 700 行以内（拆分前 part_selector 是 1528 行）。"""
    over = []
    for m in PART_LAYERS + ["part_selector"]:
        p = pathlib.Path(importlib.import_module("app.services." + m).__file__)
        n = len(p.read_text(encoding="utf-8").splitlines())
        if n > PART_LINE_BUDGET:
            over.append(f"{m}={n}")
    assert not over, "配件层又长回去了：" + repr(over)


def test_search_and_drill_tools_stay_separated():
    """检索（回库取候选）与只读钻取（零写入）分居两文件，不许互相回锅（2026-09-11 拆分）。"""
    from app.services import skill_tools_kp, skill_tools_open
    search_only = ("_zero_reason", "_search_kp_parts_by_rows",
                   "tool_query_parts")
    drill_only = ("_brief_specs", "_spec_profile",
                  "_grep_hit", "_snippet", "tool_open_part", "tool_open_row",
                  "tool_open_category", "tool_grep_parts", "tool_inspect_parts")
    leaked = [f"skill_tools_kp::{n}" for n in drill_only if hasattr(skill_tools_kp, n)]
    leaked += [f"skill_tools_open::{n}" for n in search_only if hasattr(skill_tools_open, n)]
    assert not leaked, "检索/钻取工具混居：" + repr(leaked)
