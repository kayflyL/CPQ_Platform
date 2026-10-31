# -*- coding: utf-8 -*-
"""engine_boundary —— 引擎边界法（位置即法律版，2026-11-01 目录拆分）。

引擎住在仓库根 ai-office/ai_office 包里，宿主住在 backend/app（services+api）。
**位置自声明**：新文件落在哪棵树，法律就按哪套管，不需要登记（声明清单最大的
盲区=新写的引擎逻辑落进没声明的文件，守卫看不见它；目录拆分后此盲区关闭）。

三层词汇（ABI 分册五：loop/state/harness/server/host）：
  KERNEL 冻结内核   app.core / app.models / app.repository——数据库与配置基建，
                    引擎宿主共用（13 个引擎模块在用）。进程拆分时它变成
                    「宿主向引擎提供的存储接口」，是第一优先收口点。
  STRICT 严格区     import 方向已干净的引擎模块：①不得 import app.api/**；
                    ②不得 import app.services/**（宿主）；③内核允许。违者测试红，
                    无 report/enforce 之分。
  FUSED  融合区     确属引擎机制、但还带着宿主边（app.services 业务 import）的模块。
                    report 模式（默认）打印边=解耦工作清单；enforce 后带边即红。
                    解耦完→升严格区（升区棘轮守卫自动点名）。

L4 基线快照：融合区现有宿主边已拍快照——**新增边=红**（谁往引擎里新增宿主依赖，
测试当场拦），解掉的边=提醒删基线并升区。等待拉动的窗口期清单只许变小不许变大。

宿主可以自由 import 引擎（ai_office.*）——方向只能是宿主→引擎，反向才违法。
"""

# 层词汇：loop(大脑循环) / state(状态运行时) / harness(机制层) / server(服务层)
STRICT_MODULES = {
    # ── loop：大脑循环与工具执行 ──
    "agent_react": "loop",              # 大脑循环（工具目录构建器注入口解耦后升区——loop 层零宿主边）
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
    "human_query": "harness",           # 问答协议（广播器注入口解耦后升区——协议零依赖 hub）
    "skill_decision_gate": "harness",   # 决策闸（候选供给者回调化后升区——闸机制零配件域知识）
    "skill_target_contract": "harness",  # 插头解释器机制（域 formatter 迁回 requirement_slots 自注册后升区）
    "agent_write_confirm": "harness",   # 两阶段确认存证（confirm_policy_for 归位声明表后升区）
    "access_kernel": "harness",         # 权限谓词内核（自 deps 下沉；api 反向引用它=合法方向）
    "data_boundary": "harness",         # 数据边界（user_price_ok 改引 access_kernel 后升区）
    "skill_node_artifacts": "harness",  # 产物注册表机制（v4 第 1 步：CPQ builder 迁宿主 cpq_artifact_builders 自注册后升区）
    "flow_validation": "harness",       # 流校验器（E3 改查 builder_kinds，上游升区后链式升区 2026-10-31）
}

FUSED_MODULES = {
    # 每条：层 + 已知融合点与解耦方向（解耦完→升严格区）。
    # 2026-10-31 首批升区：transaction_engine / skill_node_state / agent_write_confirm /
    # data_boundary（+ 新 access_kernel 入区）。二批：human_query / skill_decision_gate。
    # 三批：agent_react（loop 层清零宿主边）。四批（v4 第 1 步）：
    # skill_node_artifacts / flow_validation（builder 迁宿主注册，2026-10-31 升区）。
    # 2026-11-01 全体随目录拆分迁入 ai-office 树，宿主边按基线快照冻结。
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
    "skill_signals": ("harness", "信号耦合 part_selector/skill_phases——解耦：信号源回调"),
    "skill_node_plugins": ("harness", "插件接线层 import 宿主阶段族——解耦：宿主启动时注册，内核只留接口"),
    "office_events": ("server", "事件总线耦合 office_governance/hub/memory——解耦：订阅端口注入"),
    "skill_config_bootstrap": ("state", "启动引导耦合 capability_spec——解耦：种子数据经配置"),
}

# 融合区宿主边基线（v4 第 1 步快照锁，2026-10-31；2026-11-01 随目录拆分迁移，值不变）：
# 等待拉动期间清单只许变小不许变大。解掉的边=提醒把基线一并删掉并考虑升区；
# 模块升区时，从 FUSED_MODULES 和本基线同时拿掉。宿主边 = app.services/app.api 全部。
FUSED_EDGE_BASELINE: dict = {
    "transaction_turn": {"api": [], "host": ["app.services.agent_tool_specs", "app.services.assistant_hub"]},
    "colleague_prompt": {"api": [], "host": ["app.services.ai_colleague_service"]},
    "colleague_turn_io": {"api": [], "host": ["app.services.assistant_hub"]},
    "colleague_turn_runners": {"api": [], "host": ["app.services.assistant_hub", "app.services.office_access",
                                                   "app.services.office_governance", "app.services.office_mission"]},
    "skill_chat": {"api": [], "host": ["app.services.capabilities", "app.services.part_selector",
                                       "app.services.portal_flow_adapter", "app.services.skill_phases",
                                       "app.services.skill_tools_fill", "app.services.slot_contract"]},
    "skill_plan_runtime": {"api": [], "host": ["app.services.capability_spec", "app.services.portal_flow_adapter",
                                               "app.services.slot_contract"]},
    "skill_turn_engine": {"api": [], "host": ["app.services.data_range_follow", "app.services.part_selector",
                                              "app.services.portal_flow_adapter", "app.services.requirement_knowledge"]},
    "skill_node_runtime": {"api": [], "host": ["app.services.artifact_render", "app.services.capabilities",
                                               "app.services.plan_builder", "app.services.portal_flow_adapter",
                                               "app.services.report_pdf", "app.services.storage_adapter"]},
    "skill_memory": {"api": [], "host": ["app.services.agent_tool_specs", "app.services.part_selector",
                                         "app.services.portal_flow_adapter"]},
    "skill_signals": {"api": [], "host": ["app.services.capabilities", "app.services.part_selector",
                                          "app.services.skill_phases", "app.services.slot_contract"]},
    "skill_node_plugins": {"api": [], "host": ["app.services.agent_tool_specs", "app.services.capabilities",
                                               "app.services.data_tools", "app.services.part_selector",
                                               "app.services.portal_flow_adapter", "app.services.skill_phases",
                                               "app.services.slot_contract"]},
    "office_events": {"api": [], "host": ["app.services.office_governance", "app.services.office_hub",
                                          "app.services.office_memory"]},
    "skill_config_bootstrap": {"api": [], "host": ["app.services.capability_spec"]},
}

# 冻结内核：引擎允许 import 的宿主侧基建（数据库/配置层）。进程拆分时此清单
# 逐条变成「宿主提供的存储接口」——今天它就是那道接口的雏形，只许收缩不许膨胀。
KERNEL_PACKAGES = ("app.core", "app.models", "app.repository")


def boundary_mode() -> str:
    """report（默认，融合区边只打印作工作清单）/ enforce（融合区带宿主边=红）。
    严格区违规两种模式都红——严格区=现行法，没有宽容档。"""
    import os
    return (os.environ.get("ENGINE_BOUNDARY_MODE") or "report").strip().lower()


def all_imports(source: str) -> set:
    """源码里全部顶层 import（ast 解析，注释/字符串不误报）：app.* 与 ai_office.*。"""
    import ast
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names
                       if a.name.startswith("app.") or a.name.startswith("ai_office"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("app.") or node.module.startswith("ai_office"):
                out.add(node.module)
    return out


def _imports_under(source: str, prefix: str) -> set:
    return sorted(i for i in all_imports(source) if i.startswith(prefix))


def strict_violations(module: str, source: str) -> dict:
    """严格区违规：{"api": [...], "host": [...]}。内核（app.core/models/repository）
    允许不计；宿主 = app.services/** 全部（引擎已迁出该树，任何 services import 都是宿主边）。"""
    imports = all_imports(source)
    return {
        "api": sorted(i for i in imports if i.startswith("app.api")),
        "host": sorted(i for i in imports if i.startswith("app.services.")),
    }


def kernel_imports(module: str, source: str) -> dict:
    """冻结内核依赖面（进程拆分时变成存储接口的清单，只许收缩）。"""
    imports = all_imports(source)
    out: dict = {}
    for pkg in KERNEL_PACKAGES:
        hits = sorted(i for i in imports if i.startswith(pkg))
        if hits:
            out[pkg] = hits
    return out


def fused_edges(module: str, source: str) -> dict:
    """融合区现状边：对宿主（app.services/** + app.api/**）的全部 import。"""
    imports = all_imports(source)
    return {
        "api": sorted(i for i in imports if i.startswith("app.api")),
        "host": sorted(i for i in imports if i.startswith("app.services.")),
    }


def baseline_new_edges(module: str, source: str) -> dict:
    """快照锁执法：融合区模块当前边超出基线的部分（=新增边，红）。基线没有的模块=无锁。"""
    base = FUSED_EDGE_BASELINE.get(module)
    if base is None:
        return {"api": [], "host": []}
    cur = fused_edges(module, source)
    return {
        "api": sorted(set(cur["api"]) - set(base.get("api") or [])),
        "host": sorted(set(cur["host"]) - set(base.get("host") or [])),
    }
