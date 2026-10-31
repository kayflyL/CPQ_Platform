# -*- coding: utf-8 -*-
"""engine_boundary —— 引擎边界声明（第 5 步"画边界"的唯一出处，2026-10-31）。

把"引擎是叙事"变成"引擎是法律"：本文件声明哪些模块属于引擎、属于哪一层（ABI 分册五
六层词汇），守卫 tests/test_engine_boundary.py 按此执法。

两档清单（v1 现状如实划分，融合区逐个解耦后升入严格区——升区即进度）：
  STRICT_MODULES  严格区：import 方向已干净，受法律全程保护——
                  ①不得 import app.api.*（引擎不依赖服务层）；②只能 import 严格区
                  引擎模块（不得摸宿主）。违者测试红，无 report/enforce 之分。
  FUSED_MODULES   融合区：确属引擎机制、但与宿主域（需求分析/报价）存在已知 import
                  融合的模块。report 模式（默认）打印其宿主边作为解耦工作清单；
                  ENGINE_BOUNDARY_MODE=enforce 后带边即红。某融合模块实际边清零时
                  守卫会提醒升区（清单不许烂）。

未在本文件声明的 app/services 模块默认=宿主层（CPQ 业务），可自由 import 引擎，
守卫不检查宿主（方向只能是宿主→引擎，反向才违法）。
"""

# 层词汇 = docs/引擎ABI-v0.md 分册五：loop(大脑循环) / state(状态运行时) /
# harness(机制层) / server(服务层) / host(宿主 APP)
STRICT_MODULES = {
    # ── loop：大脑循环与工具执行 ──
    "agent_tool_registry": "loop",      # 工具注册表执行器（写收尾 write_finish 唯一出口）
    "agent_tool_display": "loop",       # 工具结果 digest
    "agent_audit": "harness",           # 审计落账（fire-and-forget）
    "llm_client": "loop",               # 模型接入
    "llm_trace": "loop",                # 调用留痕
    "anthropic_channel": "loop",        # 模型通道
    # ── state：状态运行时 ──
    "transaction_engine": "state",      # 事务内核：步骤指针+案台（10-31 摘除 write_confirm 边后升区）
    "turn_breaker": "state",            # 回合熔断
    "skill_node_state": "state",        # 状态槽机制（属主注册反转后升区：plugins→state 单向）
    "skill_registry": "state",          # 流/技能目录
    # ── harness：机制层 ──
    "skill_contracts": "harness",       # 契约常量（SKILL_SESSION_DONE 等）
    "skill_types": "harness",           # 类型定义
    "skill_tool_context": "harness",    # TOOL_CTX 机制
    "tool_names": "harness",            # 工具名常量
    "reasoning_node_contract": "harness",  # 节点契约
    "workflow_ask": "harness",          # 问询机制
    "agent_write_confirm": "harness",   # 两阶段确认存证（confirm_policy_for 归位声明表后升区）
    "access_kernel": "harness",         # 权限谓词内核（自 deps 下沉；api 反向引用它=合法方向）
    "data_boundary": "harness",         # 数据边界（user_price_ok 改引 access_kernel 后升区）
}

FUSED_MODULES = {
    # 每条：层 + 已知融合点与解耦方向（解耦完→升严格区）。
    # 2026-10-31 首批升区：transaction_engine / skill_node_state / agent_write_confirm /
    # data_boundary（+ 新 access_kernel 入区）——见 git 8c797e9 后续提交。
    "agent_react": ("loop", "脑循环 import agent_tool_specs 取工具目录——解耦：目录经注册/注入"),
    "human_query": ("harness", "问答协议广播耦合 assistant_hub——解耦：广播器回调注入"),
    "flow_validation": ("harness", "E3 查 BUILDERS(skill_node_artifacts)+skill_target_contract（均为融合区引擎模块，无宿主边）——上游升区后链式升区"),
    "transaction_turn": ("state", "轮壳耦合工具目录/assistant_hub/skill_memory——解耦：现场经注入"),
    "colleague_prompt": ("state", "提示词组装耦合 ai_colleague_service——解耦：配置经注入"),
    "colleague_turn_io": ("state", "落库广播耦合 assistant_hub——解耦：io 端口注入"),
    "colleague_turn_runners": ("state", "plain 轮壳耦合 hub/office_access/office_governance/office_mission/skill_chat——解耦：依赖注入"),
    "skill_chat": ("state", "skill 聊天轮壳耦合宿主阶段族——解耦：同上"),
    "skill_plan_runtime": ("state", "图推进耦合 portal_flow_adapter/capability_spec/插件——解耦：宿主供给回调"),
    "skill_turn_engine": ("state", "回合编排耦合 data_range_follow/part_selector/requirement_knowledge——解耦：宿主供给回调"),
    "skill_step_runtime": ("state", "步骤运行时耦合宿主阶段族——解耦：同上"),
    "skill_node_runtime": ("state", "节点运行时耦合 plan_builder/report_pdf/bom_template_eval——解耦：产物渲染经注册"),
    "skill_memory": ("state", "记忆耦合 part_selector/portal_flow_adapter——解耦：摘要器回调注入"),
    "skill_target_contract": ("harness", "目标契约耦合 catalog_options/requirement_slots——解耦：候选源回调"),
    "slot_contract": ("harness", "槽契约耦合 llm_extract_enhance/part_selector——解耦：抽取器回调"),
    "skill_signals": ("harness", "信号耦合 part_selector/skill_phases——解耦：信号源回调"),
    "skill_decision_gate": ("harness", "决策闸候选检索耦合 part_search/part_selector——解耦：候选提供者回调注入（闸机制留内核）"),
    "skill_node_artifacts": ("harness", "BUILDERS 注册表内建宿主 builder（bom_template_eval/capabilities/portal_flow_adapter）——解耦：builder 宿主注册化（本就是声明架构的方向）"),
    "skill_node_plugins": ("harness", "插件接线层 import 宿主阶段族——解耦：宿主启动时注册，内核只留接口"),
    "office_events": ("server", "事件总线耦合 office_governance/hub/memory——解耦：订阅端口注入"),
    "skill_config_bootstrap": ("state", "启动引导耦合 capability_spec——解耦：种子数据经配置"),
}


def boundary_mode() -> str:
    """report（默认，融合区边只打印作工作清单）/ enforce（融合区带宿主边=红）。
    严格区违规两种模式都红——严格区=现行法，没有宽容档。"""
    import os
    return (os.environ.get("ENGINE_BOUNDARY_MODE") or "report").strip().lower()


def _app_imports(source: str) -> set:
    """源码里全部 app.* 顶层 import（ast 解析，注释/字符串不误报）。"""
    import ast
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names if a.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            out.add(node.module)
    return out


def strict_violations(module: str, source: str) -> dict:
    """严格区违规：{"api": [...], "host": [...]}。host=摸了严格区之外的 app.services 模块。"""
    imports = _app_imports(source)
    api = sorted(i for i in imports if i.startswith("app.api"))
    allowed = {f"app.services.{m}" for m in STRICT_MODULES}
    host = sorted(i for i in imports
                  if i.startswith("app.services.") and i not in allowed)
    return {"api": api, "host": host}


def fused_edges(module: str, source: str) -> dict:
    """融合区现状边：对宿主（未声明为引擎）与 api 层的全部 import。"""
    imports = _app_imports(source)
    engine = {f"app.services.{m}" for m in list(STRICT_MODULES) + list(FUSED_MODULES)}
    return {
        "api": sorted(i for i in imports if i.startswith("app.api")),
        "host": sorted(i for i in imports
                       if i.startswith("app.services.") and i not in engine),
    }
