# -*- coding: utf-8 -*-
"""宪法 → 守卫（防返工总闸）。

宪法（docs/skill studio设计思路.md 第 1 行）：
    总体原则：唯一AI大脑；拒绝硬编码；拒绝机械式正则匹配；前端可配置，拒绝黑盒运行。

这里放的不是「一次性检查」，而是**机制**——上一轮整改过、下一轮又冒出来的那类问题，
必须有一条自动守卫按住它，否则永远是「用户发现 → 返工」：

  1) CLAUSES：每条宪法条款挂在哪些守卫测试上；元测试强制一一对应（条款没守卫 = 红）。
  2) 机制文案棘轮：模型可见的「怎么做」规则句只许减不许增（PROSE_BASELINE 必须等于实测）。
  3) 迁移留痕：代码里删掉的规则，必须在左栏（DB）有同义锚点——删了没搬 = 能力丢失。
  4) 左栏不许出现已退役/已改名的工具名（把大脑指去调不存在的工具 = 必然返工）。

判定尺度（为什么只扫「祈使/流程」词）：
  - 事实层（允许留代码）：状态词、结构化键、字段名、原因码、数据驱动文案。
  - 契约层（允许留插头）：工具自身参数/前提/越界反馈（「x 必填」「y 不在清单内」）。
  - 规则层（必须住左栏）：「先调哪个工具」「该不该问客户」「怎么措辞」「不许丢弃」之类。
"""
from __future__ import annotations

import ast
import json
import pathlib
import re

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.constitution_lint import PROSE_MARKERS  # noqa: E402（唯一词表出处，与保存口共用）

BACKEND = pathlib.Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
SERVICES = APP / "services"
TESTS = BACKEND / "tests"

# ── 扫描范围：喂给大脑/客户的话术只可能从这些文件出来（机制层） ──────────────
MECHANISM_FILES = [
    "skill_node_plugins.py", "skill_tools_open.py", "skill_tools_kp.py", "skill_tools_select.py",
    "skill_tools_misc.py", "skill_tools_fill.py", "skill_tools_model.py",
    "skill_plan_runtime.py", "skill_phases.py", "skill_chat.py", "skill_turn_engine.py",
    "skill_step_runtime.py", "skill_node_state.py", "part_row_identity.py", "selection_engine.py",
    "agent_tool_specs.py", "agent_react.py", "agent_tool_handlers.py",
    # 2026-09-11 拆分：同事回合实现搬到 colleague_turn_* 家族。新文件必须一并进扫描范围，
    # 否则 900 行机制层代码会静默脱离本守卫（拆文件≠免责）。
    "colleague_turn_service.py", "colleague_prompt.py", "colleague_turn_io.py",
    "colleague_turn_runners.py",
    "colleague_memory_service.py", "office_brain.py", "office_mission.py",
    "data_tools.py",
    "llm_client.py",
    "ai_colleague_service.py",
]

# 「对大脑说怎么做」的祈使/流程词。事实句与工具参数契约不会命中。
# 词表本体已抽到 app/services/constitution_lint.py（与工具文案保存口共用，防止分叉）。

# 实测基线（2026-09-11 P5 盘点）。**只许降**：整改掉一条就把这里改成新值；
# 若实测 > 基线，说明又有人往代码里塞了一套提示词——那正是本守卫要拦的返工。
PROSE_BASELINE = {
    "skill_node_plugins.py": 0,
    "skill_tools_open.py": 0,
    "skill_tools_fill.py": 0,
    "skill_tools_select.py": 0,
    "skill_tools_misc.py": 0,
    "skill_tools_kp.py": 0,
    "skill_tools_model.py": 0,
    "skill_plan_runtime.py": 0,
    "skill_phases.py": 0,
    "skill_chat.py": 0,
    "skill_turn_engine.py": 0,
    "skill_step_runtime.py": 0,
    "skill_node_state.py": 0,
    "part_row_identity.py": 0,
    "selection_engine.py": 0,
    "agent_tool_specs.py": 0,
    "agent_react.py": 0,
    "agent_tool_handlers.py": 0,
    "colleague_turn_service.py": 0,
    "colleague_prompt.py": 0,
    "colleague_turn_io.py": 0,
    "colleague_turn_runners.py": 0,
    "office_brain.py": 0,
    "office_mission.py": 0,
    "data_tools.py": 0,
    "colleague_memory_service.py": 0,
    "llm_client.py": 0,
    "ai_colleague_service.py": 0,
}

# 已从代码搬进左栏的规则：锚点必须能在左栏文本里找到（搬走≠删掉）。
# 新增一行 = 你从代码里删了一条规则，并把同义句写进了左栏。
# 2026-09-11 用户裁定：「提示词（高级）」整块退役（behavior.brain/mission/charter 的键全删），
# 原先挂在这些键上的 9 条锚点一并撤销——属**有意退役**，不是丢失（口径见 docs/需求分析skill-技术架构.md §19.4）。
MOVED_RULES = [
    ("绝不静默丢弃配件行", "静默丢弃", "任务规则 9"),
    ("客户决策一回合一卡", "一次只问一个", "任务规则 12"),
    ("零召回不等于库里没有", "禁止断言库里没有", "任务规则 15"),
    ("机型从候选池内取值", "池内取值", "任务规则 14"),
    ("登记不既填又追问", "既填又追问", "任务规则 13"),
    ("登记严格按客户原话", "按客户原话", "任务规则 13"),
    ("按 steps 顺序推进（引擎硬校验）", "无法收口推进", "任务规则 18"),
    ("推断的前提字段须先经客户确认", "才能进配件选型", "任务规则 19"),
    ("目录缺口优先确认服务器类型", "优先确认「服务器类型」", "任务规则 13"),
    ("无价权角色的价格纪律", "成本核算或方案助手", "任务规则 20"),
    ("缺口转述的顾问口吻与上下文措辞", "以顾问口吻用一两句自然中文确认第一个缺口", "任务规则 21"),
    ("机器代号不得出现在对客户的话里", "系统内部代号不得出现在对客户的话里", "任务规则 21"),
    ("推荐必须逐字取选项 label", "推荐必须逐字取选项 label", "任务规则 21"),
    ("点选确认后先确认收到再转缺口", "先用一句话自然确认收到", "任务规则 21"),
    ("引擎校验反馈要照反馈修正重试", "照反馈修正参数", "任务规则 22"),
    ("库内确无该行要的料 → 客户三选一拍板", "「改平台／换料／保持原需求」", "任务规则 23"),
    ("检索不全类目浏览", "不全类目浏览", "任务规则 15"),
    ("其余目录字段可推断登记但须说明依据", "其余目录字段可依据", "任务规则 19"),
    ("收尾汇报纪律", "收尾汇报纪律", "任务规则 24"),
    ("同名料号多命中回候选", "同名料号", "任务规则 15"),
]

# ── 宪法条款 → 守卫 ───────────────────────────────────────────────────────
CLAUSES = [
    {
        "id": "C1",
        "text": "唯一 AI 大脑：模型看到的「怎么做」只来自左栏任务规则，代码不备第二套",
        "guards": [
            "test_no_injected_protocol_constants_in_code",
            "test_node_prose_layers_are_purged",
            "test_no_reverse_writer_pushes_prompt_text_into_db",
            "test_live_system_prompt_is_built_from_db_text",
            "test_mechanism_prose_only_shrinks",
            "test_migrated_rules_have_a_left_panel_anchor",
            "test_no_code_side_fallback_prompts",
        ],
    },
    {
        "id": "C2",
        "text": "拒绝硬编码：换节点/换工具 = 换配置，编排壳不认识任何节点名",
        "guards": [
            "test_orchestration_shell_has_no_node_name_dispatch",
            "test_registry_declares_every_brain_node",
            "test_register_is_the_only_extension_point",
        ],
    },
    {
        "id": "C3",
        "text": "拒绝机械式正则匹配：行/候选的归并一律按身份，不按措辞猜",
        "guards": [
            "test_stamp_is_idempotent_and_never_merges_by_text",
            "test_resolve_row_ref_rejects_drifted_wording_instead_of_guessing",
            "test_ask_user_rejects_drifted_wording_instead_of_guessing",
            "test_select_parts_rejects_drifted_row_ref_without_declaring_a_row",
        ],
    },
    {
        "id": "C4",
        "text": "前端可配置、拒绝黑盒：任务规则改左栏即生效，引擎只摆事实",
        "guards": [
            "test_kp_turn_prompt_is_drawer_driven_and_rows_carry_answers",
            "test_pause_payload_is_facts_only",
            "test_every_pause_broadcast_goes_through_single_emitter",
        ],
    },
    {
        "id": "C5",
        "text": "下游永不回填上游：线索登记表属主落定即冻结，下游只读",
        "guards": [
            "test_freeze_flags_downstream_write_and_ignores_owner",
            "test_frozen_doc_view_blocks_every_write_path",
            "test_downstream_node_turn_gets_readonly_registration_doc",
        ],
    },
    {
        "id": "C6",
        "text": "配置即真相：左栏/配置层不许留已改名或已退役的工具名",
        "guards": ["test_left_panel_uses_current_tool_names"],
    },
]


# ── 扫描内核 ─────────────────────────────────────────────────────────────
def scan_prose(path: pathlib.Path):
    """返回 [(行号, 命中词, 原句)]。只扫字符串常量，跳过模块/函数 docstring。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docs:
            continue
        text = node.value
        if not re.search(r"[\u4e00-\u9fff]", text):
            continue
        hit = [m for m in PROSE_MARKERS if m in text]
        if hit:
            out.append((node.lineno, "、".join(hit), text))
    return out


def _collect_test_names() -> set:
    names = set()
    for p in sorted(TESTS.glob("test_*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def _left_panel_text() -> str:
    """配置层文本 = 生效流程（任务规则/节点规则）+ 节点默认契约 + 节点覆盖配置
    + 员工提示词（system_config.ai_colleagues：每个角色的 system_prompt，Manage Teams · 员工可改）。"""
    from app.models.base import Rules_SessionLocal
    from app.services.reasoning_node_contract import node_defaults
    chunks = [json.dumps(node_defaults(), ensure_ascii=False)]
    s = Rules_SessionLocal()
    try:
        rows = s.execute(_sa_text("SELECT graph FROM rules.reasoning_flow WHERE is_active IS TRUE")).fetchall()
        chunks += [json.dumps(r[0], ensure_ascii=False) for r in rows]
        rows = s.execute(_sa_text("SELECT config FROM rules.reasoning_node_config")).fetchall()
        chunks += [json.dumps(r[0], ensure_ascii=False) for r in rows]
        rows = s.execute(_sa_text("SELECT value FROM rules.system_config"
                                  " WHERE key IN ('ai_colleagues', 'ai_assistant_config')")).fetchall()
        chunks += [json.dumps(r[0], ensure_ascii=False) for r in rows]
    finally:
        s.close()
    return "\n".join(str(c) for c in chunks)


def _sa_text(sql: str):
    import sqlalchemy as sa
    return sa.text(sql)


# ── 守卫 ─────────────────────────────────────────────────────────────────
def test_every_constitution_clause_has_a_guard():
    """元测试：宪法每条款必须挂在真实存在的守卫测试上（条款没守卫 = 红）。"""
    known = _collect_test_names()
    assert CLAUSES, "宪法条款表被清空了"
    for clause in CLAUSES:
        assert clause.get("guards"), f"{clause['id']} 没有守卫测试：{clause['text']}"
        missing = [g for g in clause["guards"] if g not in known]
        assert not missing, f"{clause['id']} 引用了不存在的守卫 {missing}（重命名守卫时要同步改 CLAUSES）"
    declared = {g for c in CLAUSES for g in c["guards"]}
    assert "test_mechanism_prose_only_shrinks" in declared


def test_no_code_side_fallback_prompts():
    """宪法 C1：代码里不许再出现「模型可见的提示词常量」（兜底/第二套一律删）。

    允许留在代码里的中文只有两类：事实（状态词/字段名/原因码）与契约（参数必填/越界/输出格式）。
    这里只咬「提示词形状」的常量名 + 已被删除的旧符号不许复活。
    扫描范围是 app/**（含 api/）——`api/assistant.py:_DEFAULT_OPENING` 就是漏在 services/ 之外的教训。
    """
    banned_names = ("DEFAULT_SYSTEM_PROMPT", "_DISPATCH_SYSTEM_PROMPT", "_EXTRACT_SYSTEM",
                    "AGENT_SYSTEM_PROMPT", "NATIVE_TOOL_SYSTEM_HINT", "_DEFAULT_CHAT_SYSTEM_PROMPT",
                    "_DEFAULT_OPENING")
    hits = []
    for p in sorted(APP.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        src = p.read_text(encoding="utf-8")
        for name in banned_names:
            if name in src:
                hits.append(f"{p.name}: 禁用符号 {name} 复活（提示词只能住配置层）")
        tree = ast.parse(src)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if not isinstance(t, ast.Name):
                    continue
                looks_like_prompt = any(k in t.id.upper() for k in ("PROMPT", "PERSONA", "SYSTEM"))
                if not looks_like_prompt:
                    continue
                text = " ".join(
                    n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                )
                if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 12:
                    hits.append(f"{p.name}:{node.lineno} {t.id} 是代码里的提示词常量")
    assert not hits, "提示词只有一个出处（配置层 / 前端可见）；代码侧兜底常量必须删除：\n" + "\n".join(hits)


def test_mechanism_prose_only_shrinks():
    """机制文案棘轮：代码里「教大脑怎么做」的成段句子只许减不许增。"""
    actual = {}
    detail = {}
    for name in MECHANISM_FILES:
        p = SERVICES / name
        assert p.exists(), f"机制文件消失：{name}（改名请同步 MECHANISM_FILES）"
        hits = scan_prose(p)
        actual[name] = len(hits)
        if hits:
            detail[name] = hits
    grew = {k: (PROSE_BASELINE.get(k), v) for k, v in actual.items() if v > PROSE_BASELINE.get(k, 0)}
    assert not grew, ("代码里又长出机制文案（提示词唯一出处是左栏）。规划：文件=基线→实测\n"
                      + json.dumps(grew, ensure_ascii=False, indent=2)
                      + "\n命中原句：\n"
                      + "\n".join("%s:%s %s" % (f, ln, t[:120])
                                   for f, hits in detail.items() for ln, _m, t in hits
                                   if f in grew))
    shrank = {k: (PROSE_BASELINE.get(k), v) for k, v in actual.items() if v < PROSE_BASELINE.get(k, 0)}
    assert not shrank, ("机制文案已清理但基线没跟着降——棘轮必须咬住进度，请把 PROSE_BASELINE 改成实测值：\n"
                        + json.dumps(shrank, ensure_ascii=False, indent=2))
    stale = [k for k in PROSE_BASELINE if k not in MECHANISM_FILES]
    assert not stale, f"PROSE_BASELINE 里有已不在扫描范围的文件：{stale}"


def test_migrated_rules_have_a_left_panel_anchor():
    """迁移留痕：从代码里搬走的规则，左栏必须找得到同义句（搬走 ≠ 删掉）。"""
    text = _left_panel_text()
    missing = [f"{rid}（锚点「{anchor}」不在左栏，原定位置：{home}）"
               for rid, anchor, home in MOVED_RULES if anchor not in text]
    assert not missing, "规则只从代码删了、没搬进左栏，等于能力丢失：\n" + "\n".join(missing)


def test_left_panel_uses_current_tool_names():
    """左栏/配置层不许出现已改名或已退役的工具名（大脑被指去调不存在的工具）。"""
    from app.services.tool_names import RETIRED_TOOL_IDS, TOOL_RENAME_MAP
    bad = sorted(set(TOOL_RENAME_MAP) | set(RETIRED_TOOL_IDS))
    pat = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(b) for b in bad) + r")(?![A-Za-z0-9_])")
    found = sorted({m.group(1) for m in pat.finditer(_left_panel_text())})
    assert not found, ("左栏/配置层还在引用旧工具名 %s —— 跑 "
                       "scripts/migrate_left_panel_tool_names_20260911.py 归一。" % found)
