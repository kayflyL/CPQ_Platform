# -*- coding: utf-8 -*-
"""engine_boundary —— 引擎边界法（位置即法律版，2026-11-01 目录拆分）。

引擎住在仓库根 ai-office/ai_office 包里，宿主住在 backend/app（services+api）。
**位置自声明**：新文件落在哪棵树，法律就按哪套管，不需要登记（声明清单最大的
盲区=新写的引擎逻辑落进没声明的文件，守卫看不见它；目录拆分后此盲区关闭）。

两层词汇（ABI 分册五：loop/state/harness/server/host）：
  KERNEL 冻结内核   app.core / app.models / app.repository——数据库与配置基建，
                    引擎宿主共用（13 个引擎模块在用）。进程拆分时它变成
                    「宿主向引擎提供的存储接口」，是第一优先收口点。
  STRICT 严格区     引擎模块（=引擎树全部）：①不得 import app.api/**；
                    ②不得 import app.services/**（宿主）；③内核允许。违者测试红。

引擎取宿主能力的唯一合法通道 = host_ports 端口（宿主 engine_wiring 接线）。
曾经的融合区（FUSED）过渡机制已于 2026-11-01 退役：45 条宿主边全部改经端口、
融合区清零后脚手架拆除（迁移史与 45 边分账见 docs/引擎独立欠账台账.md）。
引擎新文件带宿主边 = 当场违规，没有自助申报通道——真遇到端口解不开的边，
那是架构决策，停下拍板，不是改配置。

宿主可以自由 import 引擎（ai_office.*）——方向只能是宿主→引擎，反向才违法。
"""
import ast

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
    "host_ports": "harness",            # 宿主端口注册表（融合区预解的引擎侧唯一取用面，2026-11-01）
    # ── 2026-11-01 融合区预解：45 条宿主边全部改经 host_ports 端口（engine_wiring 接线），
    #    整族升严格区。融合区自此清零——S2 的引擎/宿主分界线在 import 层完整成立。──
    "transaction_turn": "state",        # 事务回合壳（hub 广播/工具目录经端口）
    "colleague_prompt": "state",        # 提示词组装（同事配置/记忆块经端口）
    "colleague_turn_io": "state",       # 回合落库广播（hub 经端口）
    "colleague_turn_runners": "state",  # 同事回合族（hub/权限/治理/任务经端口）
    "skill_chat": "state",              # skill 聊天轮壳（登记契约/选型/阶段经端口）
    "skill_plan_runtime": "state",      # 图推进（能力声明/登记适配经端口）
    "skill_turn_engine": "state",       # 回合编排（需求知识/数据范围/选型经端口）
    "skill_step_runtime": "state",      # 步骤运行时
    "skill_node_runtime": "state",      # 节点运行时（方案构建/报告渲染/持久化经端口）
    "skill_memory": "state",            # 记忆（登记适配/选型/工具注记经端口）
    "skill_signals": "harness",         # 信号（登记契约/能力回填/选型信号经端口）
    "skill_node_plugins": "harness",    # 插件接线层（阶段族/选型/登记契约经端口）
    "office_events": "server",          # 事件总线（治理/状态hub/记忆经端口）
    "skill_config_bootstrap": "state",  # 启动引导（能力声明经端口）
}

# 冻结内核：引擎允许 import 的宿主侧基建（数据库/配置层）。进程拆分时此清单
# 逐条变成「宿主提供的存储接口」——今天它就是那道接口的雏形，只许收缩不许膨胀。
KERNEL_PACKAGES = ("app.core", "app.models", "app.repository")


def all_imports(source: str) -> set:
    """源码里全部顶层 import（ast 解析，注释/字符串不误报）：app.* 与 ai_office.*。
    `from app.services import x` 名单形态展开成 app.services.x——2026-11-01 修复：
    裸包名形态此前只记 app.services，逃过宿主边计数（colleague_prompt 的
    colleague_memory_service 边就是这么漏进基线的）。"""
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names
                       if a.name.startswith("app.") or a.name.startswith("ai_office"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("app.") or node.module.startswith("ai_office"):
                out.add(node.module)
                if node.module in ("app", "app.services", "ai_office", "app.api"):
                    out.update(f"{node.module}.{a.name}" for a in node.names
                               if a.name and a.name != "*")
    return out


def strict_violations(module: str, source: str) -> dict:
    """严格区违规：{"api": [...], "host": [...]}。内核（app.core/models/repository）
    允许不计；宿主 = app.services/** 全部（引擎已迁出该树，任何 services import 都是
    宿主边）——无例外条款，引擎取宿主能力一律走 host_ports 端口（2026-11-01
    组合根白名单清除：原 transaction_engine/skill_node_artifacts 两条惰性自举
    上收宿主 engine_wiring）。"""
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
