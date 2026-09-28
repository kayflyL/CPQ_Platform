# -*- coding: utf-8 -*-
"""同事回合拆分守卫（2026-09-11 P6）。

背景：`colleague_turn_service.py` 曾把「配置/提示词组装 + 落库广播 + 三种执行器 +
串行队列」四件事堆在 1122 行里。拆成 4 个模块后，本守卫拦三件事：

1. **谁在哪**：拆出的名字必须住在归属模块里，不许回锅进薄壳；
2. **多大**：薄壳只留队列 + 总入口，不许再长出实现；
3. **方向**：依赖只能单向（prompt ← io ← runners ← service），不许反向或成环。

拆文件不难，难的是不长回去——这些断言就是「又长回去了」的报警器。
"""
import ast
import importlib
import inspect
import pathlib

# 归属表：函数名 -> 应该住在哪个模块
OWNERS = {
    "colleague_prompt": [
        "_skill_library", "_resolved_skills", "_has_workflow_skills",
        "_effective_tool_ids", "build_chat_config",
        "_style_hint", "_skill_prompt", "_workflow_hint", "_handoff_hint",
        "_memory_policy", "_short_term_history", "_skill_for_tool", "_memory_block",
        "_user_name", "_base_messages",
    ],
    "colleague_turn_io": [
        "_persist_and_broadcast", "_add_assistant_message", "_trace",
        "_ensure_ai_office_opportunity",
    ],
    "colleague_turn_runners": [
        "_broadcast_chat_progress", "_run_plain_turn", "_first_workflow_skill",
        "_skill_phase_hint", "_run_tool_turn", "_skill_chat_memory_active",
        "_run_skill_chat", "_skill_write_mode",
    ],
    "colleague_turn_service": [
        "_drain_thread_queue", "_clear_thread_queue", "run_colleague_turn",
    ],
}

# 薄壳允许存在的实现（新增 = 你往壳里塞了实现，请搬到语义模块）
# turn_active（2026-09-13）：_THREAD_TURN_ACTIVE 集合的只读访问器，与队列/锁同属
# 回合运行态事实（排队不算在跑），服务端给前端看门狗判终态用——留在壳里与队列作伴。
SHELL_ALLOWED_DEFS = {"_drain_thread_queue", "_clear_thread_queue", "run_colleague_turn",
                      "turn_active"}

# 依赖方向：索引小的不许 import 索引大的
LAYERS = ["colleague_prompt", "colleague_turn_io", "colleague_turn_runners",
          "colleague_turn_service"]
LINE_BUDGET = 700
SHELL_LINE_BUDGET = 300

# 拆分前的外部导入路径必须继续可用（重导出）
REEXPORTS = [
    "run_colleague_turn", "_clear_thread_queue", "_drain_thread_queue",
    "_THREAD_TURN_LOCKS", "_THREAD_TURN_QUEUE",
    "_skill_library", "_handoff_hint", "_has_workflow_skills", "_skill_phase_hint",
    "assistant_hub", "SKILL_SESSION_ACTIVE",
]


def _mod(name):
    return importlib.import_module("app.services." + name)


def _src(name) -> str:
    return pathlib.Path(_mod(name).__file__).read_text(encoding="utf-8")


def _top_defs(name):
    return [n.name for n in ast.parse(_src(name)).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def test_each_split_module_owns_its_names():
    """拆出的名字必须住在归属模块里（改名搬家要同步这里的归属表）。"""
    missing = []
    for mod_name, names in OWNERS.items():
        mod = _mod(mod_name)
        missing += [f"{mod_name}::{n}" for n in names if not hasattr(mod, n)]
    assert not missing, "拆出的名字不在归属模块里：" + repr(missing)


def test_service_is_a_thin_shell():
    """薄壳只留队列 + 总入口：不许再长出实现（回锅即红）。"""
    defs = set(_top_defs("colleague_turn_service"))
    extra = sorted(defs - SHELL_ALLOWED_DEFS)
    assert not extra, ("colleague_turn_service 又长出实现（应搬到语义模块，"
                       "或在此显式登记）：" + repr(extra))
    size = len(_src("colleague_turn_service").splitlines())
    assert size <= SHELL_LINE_BUDGET, f"薄壳又长回 {size} 行（预算 {SHELL_LINE_BUDGET}）"


def test_modules_stay_within_line_budget():
    """拆完别再长回去：每个模块 700 行以内（拆分前 colleague_turn_service 是 1122 行）。"""
    over = []
    for m in LAYERS:
        n = len(_src(m).splitlines())
        if n > LINE_BUDGET:
            over.append(f"{m}={n}")
    assert not over, "同事回合层又长回去了：" + repr(over)


def test_layer_direction_never_reverses():
    """依赖只能向下（prompt ← io ← runners ← service）：不许反向或成环。"""
    idx = {m: i for i, m in enumerate(LAYERS)}
    bad = []
    for m in LAYERS:
        for node in ast.walk(ast.parse(_src(m))):
            if isinstance(node, ast.ImportFrom):
                dep = (node.module or "").rsplit(".", 1)[-1]
                if dep in idx and idx[dep] >= idx[m]:
                    bad.append(f"{m}->{dep}")
    assert not bad, "同事回合层出现反向/同层依赖：" + repr(sorted(set(bad)))


def test_legacy_import_paths_still_resolve():
    """原导入路径（app.services.colleague_turn_service.X）必须继续可用，不许悄悄改门牌。"""
    shell = _mod("colleague_turn_service")
    missing = [n for n in REEXPORTS if not hasattr(shell, n)]
    assert not missing, "薄壳丢了重导出（老调用方会 ImportError）：" + repr(missing)


def test_entrypoint_stays_a_reasonable_shell():
    """总入口 run_colleague_turn 只做编排，不许重新长成怪物。"""
    fn = _mod("colleague_turn_service").run_colleague_turn
    size = len(inspect.getsource(fn).splitlines())
    assert size <= 150, f"run_colleague_turn 又长回 {size} 行（预算 150）"
