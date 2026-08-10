"""Repository for rules.reasoning_flow + reasoning_node_config。

仿 strategy_repo 模式。提供 active 流读取、图/节点 config upsert、版本切换、默认 seed。
延迟 import requirement_intel_service / candidate_search 的模块常量（避免循环 import）。
"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.reasoning_flow import ReasoningFlow, ReasoningNodeConfig



# 默认图结构 v12（单路能力链，2026-08 重构·实测迭代）—— 执行走 Graph Orchestrator。
# understand → gap_analyze → scene_decide → model_reason → kp_reason → spec_compliance →
# compose → budget_check → llm_audit → audit_fix → review。
# 反问循环：gap_analyze --(缺口)--> llm_ask --(答完回)--> understand（补充后整链重跑）。
# 自纠回边：budget_check 超预算 → 自动降配（确定性，重跑 kp 代表件/compose）；
#           audit_fix 检出问题 → 重跑 kp_reason/spec_compliance/compose/budget_check/llm_audit（上限可配）。
# 删除 cond_gap（orchestrator 不执行条件节点，缺口→反问由编排器决策，避免画布与执行不一致）。
# AI 开：understand/llm_ask/scene_decide/model_reason/kp_reason/llm_audit 走 LLM 增强 + ReAct 工具决策；
# AI 关/失败：各节点内部规则兜底（source 白盒标注）。spec_compliance/compose/budget_check/review 是确定性红线。
# Phase2（2026-08 定稿）：默认链收敛为 6 节点 —— AI 员工 + 工具 + 校验。
# understand 自带「专家分析/场景/缺口」（不再依赖 gap_analyze/scene_decide）；
# kp_reason = LLM 提议 + 库校验；compose/llm_audit/review 确定性+裁判校验。
# 旧节点（gap_analyze/scene_decide/spec_compliance/budget_check/audit_fix/extract）保留在 palette
# 作为可选能力，用户拖回画布即参与执行（图=能力注册表，天然可回退）。
DEFAULT_GRAPH_V11 = {
    "nodes": [
        {"id": "understand", "type": "understand", "label": "需求理解+专家分析", "position": {"x": 0, "y": 200}},
        {"id": "llm_ask", "type": "llm_ask", "label": "智能反问", "position": {"x": 280, "y": 60}},
        {"id": "model_reason", "type": "model_reason", "label": "机型推理（多级放宽）", "position": {"x": 560, "y": 200}},
        {"id": "kp_reason", "type": "kp_reason", "label": "配件提议+库校验", "position": {"x": 840, "y": 200}},
        {"id": "compose", "type": "compose", "label": "方案组装（确定性）", "position": {"x": 1120, "y": 200}},
        {"id": "llm_audit", "type": "llm_audit", "label": "方案校对（独立裁判）", "position": {"x": 1400, "y": 200}},
        {"id": "review", "type": "review", "label": "方案就绪", "position": {"x": 1680, "y": 200}},
    ],
    "edges": [
        {"id": "p2e0", "source": "understand", "target": "model_reason"},
        {"id": "p2e1", "source": "model_reason", "target": "kp_reason"},
        {"id": "p2e2", "source": "kp_reason", "target": "compose"},
        {"id": "p2e3", "source": "compose", "target": "llm_audit"},
        {"id": "p2e4", "source": "llm_audit", "target": "review"},
    ],
}


def _type_packages_defaults(pkgs: list) -> list:
    """给类型套餐打「强制核心件」标记（配置驱动，拒绝硬编码）：
      - 存储类套餐 mandatory_storage=True（硬盘是存储服务器核心，需求没提也配代表盘）；
      - AI 类套餐 mandatory_gpu=True（AI/加速计算服务器核心是 GPU，配件库有卡就配，2026-08 修）。
    只改命中关键词的套餐，其他套餐不动；无套餐时用默认三套。"""
    pkgs = [dict(p) for p in pkgs]
    if not any("存储" in (p.get("type_keyword") or "") for p in pkgs):
        pkgs = pkgs + [{"type_keyword": "存储", "categories": ["CPU", "Memory", "HDD/SSD", "Raid card"]}]
    if not any("AI" in (p.get("type_keyword") or "") for p in pkgs):
        pkgs = pkgs + [{"type_keyword": "AI", "categories": ["CPU", "GPU", "Memory", "HDD/SSD"]}]
    for p in pkgs:
        kw = p.get("type_keyword") or ""
        if "存储" in kw:
            p["mandatory_storage"] = True
        if "AI" in kw:
            p["mandatory_gpu"] = True
    return pkgs


def _default_intent_words() -> list:
    """方案助手「自然进入选配」意图词（挂 understand 节点，策略中心可配）。
    用户消息命中任一子串 → 自动进入需求分析；与前端 utils/configIntent 默认同源。"""
    return [
        "配置服务器", "配一台服务器", "配台服务器", "配个服务器", "服务器配置",
        "帮我配", "给我配", "怎么配", "要配一台", "配置一台", "做一台服务器",
        "选配", "选型", "需求分析", "生成方案", "生成bom", "整机方案", "报价", "bom",
    ]


def _ask_user_defaults() -> dict:
    """目录引导兜底默认（AI 关/失败时用）：与 catalog_guide.DEFAULT_ASK_CONFIG 同源。
    落进 v11 llm_ask 节点配置，画布抽屉可视化编辑（拒绝黑盒/硬编码在代码里）。
    """
    try:
        from app.services.catalog_guide import DEFAULT_ASK_CONFIG
        return dict(DEFAULT_ASK_CONFIG)
    except Exception:
        return {"mode": "catalog", "enabled_types": [], "recommended_type": "",
                "recommended_models": {}, "max_rounds": 6,
                "type_question": "请选择服务器类型（以下均为有货在售类型）：",
                "model_question": "请选择该类型下的在售机型：",
                "kp_intro": "请按以下格式填写需要的配件，没有的项可省略：",
                "reply_format": "CPU：型号 ×数量\n内存：容量 ×条数\nGPU：型号 ×数量\n硬盘：容量 ×数量\n预算：金额",
                "default_hint": "不确定可回复「你推荐」，或点「跳过」让我推荐"}

def _v11_node_configs() -> dict:
    """v11 节点默认配置（AI 增强优先、节点内规则兜底；全部画布可配）。"""
    # 领域知识默认（与旧 extract 同源，AI 理解 + 规则兜底共用；用户可在 understand 抽屉改）
    _legacy_extract = _default_node_configs().get("extract") or {}
    _legacy_sb = _default_node_configs().get("select_baseline") or {}
    _legacy_mk = _default_node_configs().get("match_kp") or {}
    return {
        # AI 理解：领域知识注入 + 目录白名单 + few-shot 案例
        "understand": {"system_prompt": None,
                       "case_source": "internal", "case_top_k": 2, "case_match": "tags_keyword",
                       # 自然进入选配意图词：方案助手聊到这些说法 → 自动进入需求分析（策略中心可配）
                       "intent_words": _default_intent_words(),
                       "keyword_limit": _legacy_extract.get("keyword_limit") or 12,
                       "lexicons": _legacy_extract.get("lexicons") or [],
                       "spec_aliases": _legacy_extract.get("spec_aliases") or [],
                       "qty_units": _legacy_extract.get("qty_units") or [],
                       "qty_multipliers": _legacy_extract.get("qty_multipliers") or [],
                       "model_token_regex": _legacy_extract.get("model_token_regex") or ""},
        # 缺口分析：槽位覆盖度 + LLM 可选解释
        "gap_analyze": {"llm_explain": True},
        # 缺口分支：非 explicit 且未封顶 → 反问
        "cond_gap": {"expr": "clarity != 'explicit' and not clarity_capped"},
        # 智能反问：LLM 策略提问（问最关键1个/列全）；目录选项白名单
        # workload_categories：缺场景/用途时首问工作负载（更贴业务，映射到类型），可配
        "llm_ask": {"strategy": "one", "max_rounds": 6,
                    # AI 关/失败时的目录引导兜底文案/选项 —— 显式落进节点配置，
                    # 让画布抽屉看到真实默认值（不再"看着是空的"），用户可改可存。
                    "ask_user": _ask_user_defaults(),
                    "workload_categories": [
                        {"label": "虚拟化 / 云主机", "desc": "运行多少台虚拟机？", "type": "通用计算服务器"},
                        {"label": "数据库", "desc": "SQL/NoSQL？数据量多大？", "type": "通用计算服务器"},
                        {"label": "AI / 机器学习", "desc": "训练还是推理？需要几块 GPU？", "type": "AI / 加速计算服务器"},
                        {"label": "Web / 应用服务器", "desc": "并发/在线用户量多大？", "type": "通用计算服务器"},
                        {"label": "文件 / 备份存储", "desc": "容量多大？", "type": "存储服务器"},
                        {"label": "边缘 / 分支机构", "desc": "部署环境？", "type": "通用计算服务器"},
                    ],
                    # 分档引导（P1-2）：缺 CPU/内存/存储 规格时，给规模档位参考，降低回答门槛
                    # ⚠️ recommend 必须可解析（CPU：N核 / 内存：容量×条数 / 存储：容量+接口），
                    # 否则用户点档位后理解节点抽不出来、下轮重复问同一题（实测复现修）。
                    "scale_tiers": {
                        "CPU": [
                            {"label": "小型", "desc": "访问量较低，单一应用", "recommend": "16核"},
                            {"label": "中型", "desc": "多个服务/中等流量", "recommend": "32核"},
                            {"label": "大型", "desc": "高并发/微服务", "recommend": "64核"},
                        ],
                        "内存": [
                            {"label": "入门", "desc": "少量应用", "recommend": "32G*4条"},
                            {"label": "标准", "desc": "中等负载", "recommend": "32G*8条"},
                            {"label": "高配", "desc": "内存密集", "recommend": "64G*8条"},
                        ],
                        "存储": [
                            {"label": "基础", "desc": "系统盘+少量数据", "recommend": "2×480G SSD"},
                            {"label": "标准", "desc": "业务数据", "recommend": "2×960G SSD + 2×4T SATA"},
                            {"label": "大容量", "desc": "海量存储", "recommend": "8×8T SATA"},
                        ],
                    }},
        # 场景判定：规则判定本体 + AI 增强
        "scene_decide": {"fallback_scene": "通用计算服务器", "decide_threshold": 30},
        # 机型推理：ReAct 调 select_models（LLM 决定选哪个，数据规则补全）
        "model_reason": {"enabled_tools": ["select_models"],
                         "max_iterations": 6, "max_plans": 6,
                         "recommend_strategy_id": _legacy_sb.get("recommend_strategy_id"),
                         "no_signal_strategy": _legacy_sb.get("no_signal_strategy") or "return_empty",
                         "fallback_order": _legacy_sb.get("fallback_order") or ["exact", "same_series", "same_form", "all"]},
        # 配件推理：ReAct 调 pick_kp_parts（工具结果即决策，规则精确执行）
        "kp_reason": {"enabled_tools": ["pick_kp_parts"], "max_iterations": 6,
                      "representative_pick": _legacy_mk.get("representative_pick") or "auto",
                      "spec_rules": _legacy_mk.get("spec_rules") or [],
                      "type_packages": _type_packages_defaults(_legacy_mk.get("type_packages") or []),
                      "fallback_strategy": _legacy_mk.get("fallback_strategy") or "fallback_representative",
                      "category_aliases": _legacy_mk.get("category_aliases"),
                      "cpu_mem_type_rules": _legacy_mk.get("cpu_mem_type_rules") or [],
                      "drive_spec_substitute": _legacy_mk.get("drive_spec_substitute", True)},
        "compose": {"kp_per_baseline": True},
        # 预算校验：超预算自动降配（确定性，先换 min_price 代表件→重组装→重校验；downgrade_axis.model 预留）
        "budget_check": {"underspend_threshold": 0.5, "auto_downgrade": True,
                         "downgrade_axis": ["representative_pick", "model"]},
        # 规格合规校验（v12 新增，确定性红线前）：需求规格 vs 实配 —— AI 缺卡自动补、型号降级/内存代际不符标 issue
        "spec_compliance": {"enabled": True, "mode": "auto_fix",
                            "strict_model_match": True, "gpu_required_for_ai": True,
                            "cpu_mem_generation": _legacy_mk.get("cpu_mem_type_rules") or [],
                            "max_fix_rounds": 2},
        # 审计自纠（v12 新增）：llm_audit 检出问题 → 重跑整链（含自身）再评估一次
        #（执行中自我修正闭环；上限 max_retry，默认 1 轮，重跑后仍不过 → review 人工复核）
        "audit_fix": {"enabled": True, "max_retry": 1,
                      "retry_scope": ["kp_reason", "spec_compliance", "compose", "budget_check",
                                      "llm_audit", "audit_fix"],
                      "only_critical": True},
        "llm_audit": {"reference_limit": 2},
        "review": {
            "output_preset": "standard",
            # BOM 明细输出（方案助手/企微分析结果里附的 BOM 文本）：
            # enabled=是否显示；mode=live 走用户配置的 BOM 模板（与前端一致）/ excel 平铺
            "bom_output": {"enabled": True, "mode": "live", "show_price": True,
                           "show_summary": True, "include_l6": True, "include_kp": True},
            # 推荐输出（方案助手：方案就绪后先给推荐+理由+下一步引导，BOM 附后）
            "recommendation": {"enabled": True, "style": "concise", "include_next_steps": True,
                               "next_steps": ["CPU", "内存", "存储", "网络"]},
        },
    }


def _normalize_graph(g: dict) -> dict:
    """图结构归一化到 v2（vue flow 兼容）。v1: nodes{key,label}, edges{from,to}；
    v2: nodes{id,type,label,position}, edges{id,source,target[,source_handle,target_handle,condition]}。
    缺 type 从 id/key 推；缺 position 用索引线性补；from→source / to→target 别名兼容。"""
    if not isinstance(g, dict):
        return {"nodes": [], "edges": []}
    raw_nodes = g.get("nodes") or []
    raw_edges = g.get("edges") or []
    nodes = []
    for i, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("key") or f"n{i}"
        ntype = n.get("type") or n.get("key") or "unknown"
        label = n.get("label") or nid
        pos = n.get("position") or {"x": i * 300, "y": 200}
        nn: dict = {"id": nid, "type": ntype, "label": label, "position": pos}
        if "data" in n:
            nn["data"] = n["data"]
        nodes.append(nn)
    edges = []
    for i, e in enumerate(raw_edges):
        if not isinstance(e, dict):
            continue
        src = e.get("source") or e.get("from")
        tgt = e.get("target") or e.get("to")
        if not src or not tgt:
            continue
        ee: dict = {"id": e.get("id") or f"e{i}", "source": src, "target": tgt}
        for k in ("source_handle", "target_handle", "condition", "label", "animated"):
            if k in e:
                ee[k] = e[k]
        edges.append(ee)
    return {"nodes": nodes, "edges": edges}


# 型号 token 正则（必含数字；含单字母+3位数字以匹配 H100/A100/B200）—— extract 与 llm_agent 共用
_DEFAULT_MODEL_TOKEN_REGEX = (
    r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$"
)


def _default_node_configs() -> dict:
    """默认节点 config = 当前模块常量快照（建 v1 用）。延迟 import 避免循环。"""
    from app.services.requirement_intel_service import _CN_STOPWORDS
    from app.services.requirement_normalizer import DEFAULT_NORMALIZE_CONFIG as _DEFAULT_NORMALIZE_CONFIG
    from app.api.candidate_search import CATEGORY_KP_ALIASES, MAX_PLANS, PER_KEYWORD_LIMIT
    return {
        # ── 双路线分叉节点（condition，expr 读全局 AI 开关 llm_enabled）──
        # route_fork（头部）：true(AI 开)→llm_agent、false(本地)→extract
        "route_fork": {"expr": "llm_enabled"},
        # cond_audit（尾部）：true(AI 开)→llm_audit、false(本地)→review
        "cond_audit": {"expr": "llm_enabled"},

        # AI 路需求理解主节点（P1，2026-08-07）：LLM 接管需求理解，替代 regex extract。
        # = run_agent_understand：需求原文 → catalog 白名单锚定 → LLM 出 RequirementSlots
        #   （EXTRACT_ENHANCE_SCHEMA）→ merge_into_ext 确定性合并 → ctx["ext"]。
        # 三道闸：catalog 白名单锚定 + merge 校验 + extract 确定性兜底（离线可跑）。
        # 取代旧 B2「确定性 extract + ReAct 接地」——理解不再是 regex，打地鼠从根上消失。
        # ReAct 接地降级为可选 escalation（escalate_grounding 默认关）；pick_kp_parts/build_plan 保持确定性。
        "llm_agent": {
            "system_prompt": None,            # None=用 agent_understand.AGENT_UNDERSTAND_SYSTEM_PROMPT；画布可覆盖
            "escalate_grounding": False,      # server_type 缺/弱时 ReAct 调 select_models 锁机型（默认关，靠 catalog 直抽）
            "enabled_tools": ["select_models"],   # escalate_grounding 开时用；search_cases 待 P4 CBR few-shot 接入
            "max_iterations": 5,                  # escalate 接地的 ReAct 循环上限（兜底防爆）
            "model_token_regex": _DEFAULT_MODEL_TOKEN_REGEX,  # 兜底给 match_kp（主源是 extract 节点 config）
            # CBR 案例检索参数（escalate + P4 search_cases 用，画布可配）：
            "case_source": "internal",            # internal（查 BomCase 表）/ external（以后接 RAG API）/ off（关，退零样本）
            "case_top_k": 2,                      # 检索相似案例数
            "case_match": "tags_keyword",         # 匹配方式：tags / keyword / tags_keyword
        },

        # LLM 方案校对（v8）：bom_cases 同平台 few-shot 意图级校对。仅 AI 路走（cond_audit true 边），
        # 受全局 AI 开关约束：开启后对全部方案一次调用 LLM，失败降级规则校对。
        "llm_audit": {
            "enable_llm": True,   # AI 路校对节点（受全局 AI 开关约束）
            "reference_limit": 2,  # few-shot 参考案例数（同系列优先）
        },
        # LLM 反问节点（P2）：复用目录状态机，文案由 LLM 生成（一次列全缺失项）。
        # 未在默认图（默认走 ask_user + LLM 追问注入），需要显式编排时从画布添加。
        "llm_ask": {
            "use_llm_questions": True,      # 注入 LLM 主理解的缺失项追问
        },
        # 槽位语义校验（v6 新增）：白名单外值丢弃 + LLM vs 规则冲突/低置信度收集（P2 confirm 用）
        "slot_validate": {
            "strict": True,        # 严格模式：白名单外值直接丢弃并记 issues
        },
        # 需求输入规范化（extract 前）：规则单一来源 = requirement_normalizer.DEFAULT_NORMALIZE_CONFIG
        # （画布可改，改完存节点 config 覆盖默认）
        "normalize_input": dict(_DEFAULT_NORMALIZE_CONFIG),
        "extract": {
            "keyword_limit": 12,
            "lexicons": [
                {
                    "id": "lex_kp", "name": "KP 配件词表", "kind": "kp",
                    "entries": [
                        {"key": "CPU", "triggers": ["cpu", "processor", "处理器", "epyc", "xeon", "至强", "intel", "amd", "兆芯", "开胜", "zhaoxin", "kh50000", "kh-50000", "kh5000", "kh-5000"]},
                        {"key": "Memory", "triggers": ["memory", "ram", "内存", "ddr", "rdimm"]},
                        {"key": "HDD/SSD", "triggers": ["hdd", "ssd", "nvme", "硬盘", "磁盘", "sata", "u.2", "u.3", "启动盘", "系统盘", "数据盘", "存储盘"]},
                        {"key": "GPU", "triggers": ["gpu", "显卡", "图形卡", "rtx", "l40", "w7900", "a100", "h100", "4090", "5090", "涡轮卡", "涡轮"]},
                        {"key": "Raid card", "triggers": ["raid", "阵列", "阵列卡", "mega", "brocade"]},
                        {"key": "Network(NIC) requirement", "triggers": ["nic", "网络", "网卡", "网口", "ethernet", "e810", "mlx", "connectx"]},
                        {"key": "HBA", "triggers": ["hba", "hba卡"]},
                    ],
                },
                {
                    "id": "lex_chassis", "name": "机箱底盘件词表", "kind": "chassis",
                    # key 对齐 parts_master.category（中文为主）；命中进 chassis_categories，不喂 pick_kp_parts
                    "entries": [
                        {"key": "背板", "triggers": ["背板", "backplane"]},
                        {"key": "散热器", "triggers": ["散热器", "散热", "heatsink"]},
                        {"key": "滑轨", "triggers": ["滑轨", "导轨", "rail"]},
                        {"key": "电源", "triggers": ["电源", "psu", "power"]},
                        {"key": "Cable", "triggers": ["cable", "线缆", "电源线", "数据线"]},
                        {"key": "机箱", "triggers": ["机箱", "chassis"]},
                    ],
                },
                {
                    "id": "lex_server_type", "name": "服务器类型词表", "kind": "server_type",
                    # key 对齐 server_types.name（精确匹配优先于 usage 模糊）
                    "entries": [
                        {"key": "AI / 加速计算服务器",
                         "triggers": ["ai训练", "ai 推理", "深度学习", "训练", "大模型", "llm", "gpu 算力", "推理", "infer", "部署模型", "serving",
                                      "4090", "5090", "a100", "h100", "h800", "l40", "w7900", "涡轮卡", "涡轮",
                                      "多卡", "8卡", "4卡", "双卡", "gpu整机", "加速计算", "gpu 服务器"]},
                        {"key": "存储服务器",
                         "triggers": ["存储", "对象存储", "分布式存储", "nas", "存储节点", "冷存储"]},
                        {"key": "通用计算服务器",
                         "triggers": ["虚拟化", "云主机", "容器", "k8s", "虚拟机", "openstack", "数据库", "mysql", "olap", "oltp", "oracle", "postgres", "渲染", "视觉", "特效", "影视后期", "通用", "办公", "web 服务", "业务系统"]},
                    ],
                },
                {
                    "id": "lex_series", "name": "系列词表", "kind": "series",
                    # key 对齐 system_config.server_series
                    "entries": [
                        {"key": "Orion", "triggers": ["orion", "amd", "epyc", "猎户"]},
                        {"key": "Polaris", "triggers": ["polaris", "kh5000", "kh-5000", "kh50000", "kh-50000", "开胜", "kx", "kx40000", "kx-40000", "开先", "兆芯", "zhaoxin"]},
                        {"key": "Intel", "triggers": ["intel", "xeon"]},
                        {"key": "工作站", "triggers": ["工作站", "图站"]},
                    ],
                },
                {
                    "id": "lex_form", "name": "机箱形态词表", "kind": "form",
                    "entries": [
                        {"key": "1U", "triggers": ["1u"]},
                        {"key": "2U", "triggers": ["2u"]},
                        {"key": "4U", "triggers": ["4u"]},
                        {"key": "5U", "triggers": ["5u"]},
                        {"key": "6U", "triggers": ["6u"]},
                        {"key": "8U", "triggers": ["8u"]},
                    ],
                },
            ],
            "spec_aliases": [
                {"trigger": "千兆", "category": "Network(NIC) requirement", "search_terms": ["1G", "1000M", "千兆"],
                 "spec_filter": {"spec_key": "Link Speed", "op": "=", "value": "1G"}},
                {"trigger": "万兆", "category": "Network(NIC) requirement", "search_terms": ["10G", "10000M", "万兆"],
                 "spec_filter": {"spec_key": "Link Speed", "op": "=", "value": "10G"}},
                {"trigger": "百兆", "category": "Network(NIC) requirement", "search_terms": ["100M", "百兆"],
                 "spec_filter": {"spec_key": "Link Speed", "op": "=", "value": "100M"}},
            ],
            "qty_units": [
                # 口语化数量单位 → 品类（N卡→GPU, N条→Memory, N颗/N块→CPU）
                {"unit": "卡", "category": "GPU"},
                {"unit": "条", "category": "Memory"},
                {"unit": "颗", "category": "CPU"},
                {"unit": "块", "category": "CPU"},
                {"unit": "个"},  # "2个处理器" / "8个GPU卡" / "24个DDR5"（R7：口语数量词）
            ],
            "qty_multipliers": ["*", "×"],  # 结构化清单乘号（*N / ×N）
            "model_token_regex": _DEFAULT_MODEL_TOKEN_REGEX,  # extract 与 llm_agent 共用（见模块常量）
            "stopwords": sorted(_CN_STOPWORDS),
            "engine_note": "分词引擎：jieba（内置，不可配）",
        },
        "select_baseline": {
            "max_plans": MAX_PLANS,
            "fallback_order": ["exact", "same_series", "same_form", "all"],
            "recommend_strategy_id": None,
            "no_signal_strategy": "return_empty",  # return_empty（返空让反问）/ fallback_all（硬推全量）
        },
        "match_kp": {
            "category_aliases": CATEGORY_KP_ALIASES,
            "per_keyword_limit": PER_KEYWORD_LIMIT,
            "representative_pick": "auto",
            "spec_rules": [
                # 用户没写规格时的默认下限（代表件兜底，不影响型号 token 精确命中）
                {"category": "CPU", "spec_key": "Cores", "op": ">=", "value": 16, "unit": "核"},
                {"category": "Memory", "spec_key": "Capacity", "op": ">=", "value": 16, "unit": "GB"},
                {"category": "GPU", "spec_key": "Capacity", "op": ">=", "value": 16, "unit": "GB"},
                {"category": "HDD/SSD", "spec_key": "Capacity", "op": ">=", "value": 480, "unit": "GB"},
            ],
            # CPU 型号 → 内存代际默认（需求没写 DDR 代际时按已选 CPU 推断，避免 DDR5 平台配到 DDR4）。
            # 顺序敏感、首个正则命中即定。可配：增删 CPU 型号 / 改代际映射（如新增海光/飞腾）。
            "cpu_mem_type_rules": [
                {"pattern": "KH50000|KH-50000|KH5000", "mem_type": "DDR5"},
                {"pattern": "KH40000|KH4000|KX", "mem_type": "DDR4"},
                {"pattern": "EPYC 9", "mem_type": "DDR5"},
                {"pattern": "EPYC 7", "mem_type": "DDR4"},
                {"pattern": "XEON 6", "mem_type": "DDR5"},
                {"pattern": "XEON [1-4]", "mem_type": "DDR4"},
            ],
            "type_packages": [
                # 机型类型（关键词匹配 server_type.name）→ 标准 KP 品类套餐
                {"type_keyword": "AI", "categories": ["CPU", "GPU", "Memory", "HDD/SSD"]},
                {"type_keyword": "存储", "categories": ["CPU", "Memory", "HDD/SSD", "Raid card"]},
                {"type_keyword": "通用", "categories": ["CPU", "Memory", "HDD/SSD"]},
            ],
            "fallback_strategy": "fallback_representative",  # fallback_representative/mark_unmatched/raise
            # 盘件规格属性替代（2026-08-03）：需求容量库无同名件时按 Capacity/Type 数值
            # 选替代件（同容量等级→够用最小→最接近），BOM 标注「替代」；False = 严格 unmatched。
            "drive_spec_substitute": True,
            # 容量匹配（2026-08 可配置化）：strategy=tolerance(±容差近似，默认)/strict_min(只选≥需求)；
            # AI 识别出"以上/以下"(comparison gte/lte)时按严格语义执行，不受此默认策略影响。
            "capacity_match": {"strategy": "tolerance", "tolerance": 10},
        },
        "compose": {"kp_per_baseline": True},
        "review": {},
        # v3 新增：需求明确度判定 + 反问 + 预算校验
        # 反问阈值：只有 explicit（信息齐全）才不反问；partial/unclear 都反问。
        # 旧值 "clarity == 'unclear'" 只在"几乎啥都没说"时反问，导致"我想要一台AMD服务器"(判 partial)直接放行不反问——典型模糊需求反而漏网。
        "cond_clarity": {"expr": "clarity != 'explicit' and not clarity_capped"},
        # 目录驱动引导（旧 templates_source/workload/rebuttal 已废弃）：选项 100% 来自产品目录，
        # enabled_types/recommended_type/recommended_models/reply_format 在需求中心画布可配，拒绝硬编码内容。
        "ask_user": {
            "mode": "catalog",
            "enabled_types": [],          # 启用的服务器类型（空 = 全部有货在售类型，来自 l6.server_types）
            "recommended_type": "",       # 客户答「不确定/你推荐」时的默认类型（空 = 第一个）
            "recommended_models": {},     # 类型名 → 代表性机型名（客户不选机型时用）
            "max_rounds": 6,
            "type_question": "请选择服务器类型（以下均为有货在售类型）：",
            "model_question": "请选择该类型下的在售机型：",
            "kp_intro": "请按以下格式填写需要的配件，没有的项可省略：",
            "reply_format": (
                "CPU：型号 ×数量\n"
                "内存：容量 ×条数\n"
                "GPU：型号 ×数量\n"
                "硬盘：容量 ×数量\n"
                "预算：金额"
            ),
            "default_hint": "不确定可回复「你推荐」，或点「跳过」让我推荐",
        },
        "budget_check": {"underspend_threshold": 0.5},  # 方案价/预算 低于此值提示"可升级"
        # 场景分析（v3 新增，机型选型前）：需求信号 + 商机上下文 → AI/存储/通用 × 系列 × 形态，
        # 输出带证据（白盒）。映射数据在 system_config.scene_mapping（权威、可编辑），此处 mapping 仅为兜底。
        "scene_analysis": {
            "decide_threshold": 30,   # 场景分≥此值才判定；低于回退默认场景（避免过度反问）
            "fallback_scene": "通用计算服务器",
            "mapping": None,          # None=用 system_config.scene_mapping / 模块默认；填了则读失败时兜底
        },
        # 场景未定（missing_fields 含"场景"）→ 反问补全；已定/封顶 → 正常选型
        # ⚠️ simpleeval 不支持 len()/列表字面量，用 not missing_fields 判断空列表
        "cond_scene": {"expr": "scene_determined"},  # R29：场景已确定 → 系列确认/选型；否则反问场景
        # LLM 节点（第一期：extract_enhance；question_gen/best_fit 第二期）。
    }


class ReasoningFlowRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def get_active_flow(self) -> Optional[dict]:
        """取 active 流（含 graph + node_configs 按 node_key 索引）。无 active 返回 None。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        nodes = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all()
        cfg_map = {n.node_key: (json.loads(n.config) if n.config else {}) for n in nodes}
        d = f.to_dict()
        d["graph"] = _normalize_graph(d.get("graph") or {"nodes": [], "edges": []})
        d["node_configs"] = cfg_map
        return d

    def active_is_current(self) -> bool:
        """active 流是否已是 v11 单路能力链（含 understand 节点 = 最新代）。

        防护 migrate 膨胀：active 已最新 → startup 跳过所有建流 migrate，绝不新建。
        历史教训：persistGraph 污染 + migrate 漏 guard 曾导致每次启动新建一流（#107-120 共 13 条膨胀）。
        用「节点集覆盖」而非逐节点 guard，单点兜底，任何历史 migrate 都不会再因 active 已最新而误建。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return False
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        active_ids = {n.get("id") for n in graph.get("nodes") or []}
        # v11 单路能力链（2026-08 重构）：含 understand 即视为最新代，跳过历史 migrate（防膨胀）
        return "understand" in active_ids

    def get(self, flow_id: int) -> Optional[dict]:
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        return f.to_dict() if f else None

    def list_versions(self) -> List[dict]:
        out = []
        for f in self.session.query(ReasoningFlow).order_by(ReasoningFlow.id.desc()).all():
            d = f.to_dict()
            d["node_count"] = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id
            ).count()
            out.append(d)
        return out

    def upsert_graph(self, flow_id: int, graph: dict, operator: str = "system") -> Optional[dict]:
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        f.graph = json.dumps(_normalize_graph(graph), ensure_ascii=False)
        f.version = (f.version or 1) + 1
        f.updated_at = datetime.now().isoformat()
        f.updated_by = operator
        self.session.commit()
        self.session.refresh(f)
        return f.to_dict()

    def upsert_node_config(self, flow_id: int, node_key: str, config: dict,
                           operator: str = "system") -> Optional[dict]:
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        n = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == flow_id,
            ReasoningNodeConfig.node_key == node_key,
        ).first()
        now = datetime.now().isoformat()
        if n:
            n.config = json.dumps(config, ensure_ascii=False)
            n.version = (n.version or 1) + 1
            n.updated_at = now
            n.updated_by = operator
        else:
            n = ReasoningNodeConfig(
                flow_id=flow_id, node_key=node_key,
                config=json.dumps(config, ensure_ascii=False),
                version=1, updated_at=now, updated_by=operator,
            )
            self.session.add(n)
        self.session.commit()
        self.session.refresh(n)
        return n.to_dict()

    def fix_cond_clarity_threshold(self) -> bool:
        """自愈：把 active flow 的 cond_clarity 从旧 buggy 值升级到新值。
        旧值 "clarity == 'unclear' and not clarity_capped" 只在 unclear 反问，
        导致 "我想要台AMD服务器"(判 partial) 直接放行不反问——典型模糊需求漏网。
        新值 "clarity != 'explicit' and not clarity_capped"：只有信息齐全(explicit)才不反问。
        仅当当前值恰为旧值时改，保留用户自定义。启动时调一次。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return False
        n = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id,
            ReasoningNodeConfig.node_key == "cond_clarity",
        ).first()
        if not n:
            return False
        try:
            cfg = json.loads(n.config) if n.config else {}
        except Exception:
            cfg = {}
        OLD = "clarity == 'unclear' and not clarity_capped"
        if cfg.get("expr") != OLD:
            return False
        cfg["expr"] = "clarity != 'explicit' and not clarity_capped"
        self.upsert_node_config(f.id, "cond_clarity", cfg, operator="self-heal")
        return True


    def activate(self, flow_id: int, operator: str = "system") -> Optional[dict]:
        for f in self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).all():
            f.is_active = False
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        f.is_active = True
        f.status = "active"
        f.updated_at = datetime.now().isoformat()
        f.updated_by = operator
        self.session.commit()
        self.session.refresh(f)
        return f.to_dict()

    def seed_default_if_empty(self) -> dict:
        """无任何 flow 时建 v1（= 当前硬编码），设 active。已有则返回首个。"""
        existing = self.session.query(ReasoningFlow).first()
        if existing:
            return existing.to_dict()
        now = datetime.now().isoformat()
        f = ReasoningFlow(
            name="默认推理流（单路能力链）", version=1, status="active",
            graph=json.dumps(DEFAULT_GRAPH_V11, ensure_ascii=False),
            is_active=True, description="AI-first 单路能力链：understand→model_reason→kp_reason→spec_compliance→compose→llm_audit→audit_fix→review",
            created_at=now, updated_at=now, created_by="seed", updated_by="seed",
        )
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        for node_key, cfg in _v11_node_configs().items():
            self.session.add(ReasoningNodeConfig(
                flow_id=f.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="seed",
            ))
        self.session.commit()
        return f.to_dict()


    def close(self):
        self.session.close()
