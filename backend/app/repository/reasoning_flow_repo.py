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


# 默认图结构 v6（vue flow 兼容）：v2 加 clarity_check→cond_clarity 分支 + budget_check；
# v3 加 scene_analysis（场景分析，机型选型前）+ cond_scene（场景未定→反问 / 已定→选型）；
# v4 加 normalize_input（需求输入规范化）；v6 加 llm_understand（LLM 主理解，默认关）+
# slot_validate（槽位语义校验）—— 收拢 LLM 到单一主理解节点，替代旧 extract/scene 散装增强；
# v7 加 confirm（LLM 确认面板：冲突/低置信度默认采纳、高亮可改）；
# v8 加 llm_audit（LLM 方案校对：bom_cases few-shot 意图级校对，默认关）。
# ⚠️ cond_clarity / cond_scene 的 false 边必须显式 source_handle="false"（executor 把缺省 handle 当 true）
DEFAULT_GRAPH = {
    "nodes": [
        {"id": "normalize_input", "type": "normalize_input", "label": "需求输入规范化", "position": {"x": 0, "y": 200}},
        {"id": "extract", "type": "extract", "label": "需求理解与关键词提取", "position": {"x": 300, "y": 200}},
        {"id": "llm_understand", "type": "llm_understand", "label": "LLM 主理解（可关）", "position": {"x": 450, "y": 200}},
        {"id": "slot_validate", "type": "slot_validate", "label": "槽位语义校验", "position": {"x": 600, "y": 200}},
        {"id": "confirm", "type": "confirm", "label": "LLM 确认（默认采纳）", "position": {"x": 750, "y": 200}},
        {"id": "clarity_check", "type": "clarity_check", "label": "需求明确度判定", "position": {"x": 900, "y": 200}},
        {"id": "cond_clarity", "type": "condition", "label": "明确度分支", "position": {"x": 1200, "y": 200}},
        {"id": "ask_user", "type": "ask_user", "label": "反问补全信息", "position": {"x": 1500, "y": 60}},
        {"id": "scene_analysis", "type": "scene_analysis", "label": "场景分析（AI/存储/通用）", "position": {"x": 1500, "y": 340}},
        {"id": "cond_scene", "type": "condition", "label": "场景分支", "position": {"x": 1800, "y": 340}},
        {"id": "confirm_series", "type": "confirm_series", "label": "系列确认", "position": {"x": 1980, "y": 340}},
        {"id": "select_baseline", "type": "select_baseline", "label": "机型选型（基准配置）", "position": {"x": 2250, "y": 340}},
        {"id": "match_kp", "type": "match_kp", "label": "配件匹配", "position": {"x": 2550, "y": 340}},
        {"id": "compose", "type": "compose", "label": "组合整机方案", "position": {"x": 2850, "y": 340}},
        {"id": "budget_check", "type": "budget_check", "label": "预算校验", "position": {"x": 3150, "y": 340}},
        {"id": "llm_audit", "type": "llm_audit", "label": "LLM 方案校对（可关）", "position": {"x": 3400, "y": 340}},
        {"id": "review", "type": "review", "label": "方案就绪", "position": {"x": 3750, "y": 340}},
    ],
    "edges": [
        {"id": "e1", "source": "normalize_input", "target": "extract"},
        {"id": "e1b", "source": "extract", "target": "llm_understand"},
        {"id": "e1c", "source": "llm_understand", "target": "slot_validate"},
        {"id": "e2", "source": "slot_validate", "target": "confirm"},
        {"id": "e2b", "source": "confirm", "target": "clarity_check"},
        {"id": "e3", "source": "clarity_check", "target": "cond_clarity"},
        {"id": "e4", "source": "cond_clarity", "target": "ask_user", "source_handle": "true"},
        {"id": "e5", "source": "cond_clarity", "target": "scene_analysis", "source_handle": "false"},
        {"id": "e6", "source": "scene_analysis", "target": "cond_scene"},
        {"id": "e7", "source": "cond_scene", "target": "confirm_series", "source_handle": "true"},
        {"id": "e8", "source": "cond_scene", "target": "ask_user", "source_handle": "false"},
        {"id": "e9", "source": "confirm_series", "target": "select_baseline"},
        {"id": "e10", "source": "select_baseline", "target": "match_kp"},
        {"id": "e11", "source": "match_kp", "target": "compose"},
        {"id": "e12", "source": "compose", "target": "budget_check"},
        {"id": "e12b", "source": "budget_check", "target": "llm_audit"},
        {"id": "e13", "source": "llm_audit", "target": "review"},
    ],
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


def _default_node_configs() -> dict:
    """默认节点 config = 当前模块常量快照（建 v1 用）。延迟 import 避免循环。"""
    from app.services.requirement_intel_service import _CN_STOPWORDS
    from app.services.requirement_normalizer import DEFAULT_NORMALIZE_CONFIG as _DEFAULT_NORMALIZE_CONFIG
    from app.api.candidate_search import CATEGORY_KP_ALIASES, MAX_PLANS, PER_KEYWORD_LIMIT
    return {
        # LLM 方案校对（v8 新增，2026-08 P3）：bom_cases 同平台 few-shot 意图级校对。
        # 默认关（不拖慢流程）；开启后对全部方案一次调用 LLM，失败降级规则校对。
        "llm_audit": {
            "enable_llm": False,   # 节点级开关（受「设置→AI 设置→启用 AI」总开关约束）
            "reference_limit": 2,  # few-shot 参考案例数（同系列优先）
        },
        # LLM 确认面板（v7 新增，2026-08 P2）：冲突/低置信度项默认采纳 LLM 补充、高亮可改。
        "confirm": {
            "default_decision": "accept",   # 默认采纳（前端高亮）；可选 ignore
        },
        # LLM 反问节点（P2）：复用目录状态机，文案由 LLM 生成（一次列全缺失项）。
        # 未在默认图（默认走 ask_user + LLM 追问注入），需要显式编排时从画布添加。
        "llm_ask": {
            "use_llm_questions": True,      # 注入 LLM 主理解的缺失项追问
        },
        # LLM 主理解（v6 新增，2026-08 LLM 重构 P1）：需求原文 + 目录白名单 → RequirementSlots 契约。
        # 默认关（不拖慢流程）；开启后本节点调用大模型并确定性合并（规则赢、只补缺）。
        "llm_understand": {
            "enable_llm": False,   # 节点级开关（受「设置→AI 设置→启用 AI」总开关约束）
            "max_retry": 1,        # 语义校验失败带错误喂回 LLM 的重试次数
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
            "model_token_regex": r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$",  # 型号 token 正则（必含数字；含单字母+3位数字以匹配 H100/A100/B200）
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
        },
        "compose": {"kp_per_baseline": True},
        "review": {},
        # v3 新增：需求明确度判定 + 反问 + 预算校验
        "clarity_check": {"rules_source": "requirement_rules"},  # 规则从 requirement_rules 表读
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

    def migrate_extract_model_token_regex(self) -> bool:
        """自愈：extract 的 model_token_regex 若丢了「单字母+3位数字」分支（H100/A100/R9700），
        恢复为 seed 值。该分支是型号识别的一部分，缺失会导致 GPU 型号（H100/A100/B200 等）整体丢失。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return False
        n = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id,
            ReasoningNodeConfig.node_key == "extract",
        ).first()
        try:
            cfg = json.loads(n.config) if n and n.config else {}
        except Exception:
            cfg = {}
        cur = cfg.get("model_token_regex") or ""
        if "[A-Za-z][0-9]{3,}" in cur:
            return False
        seed_cfg = _default_node_configs().get("extract") or {}
        cfg["model_token_regex"] = seed_cfg.get("model_token_regex")
        self.upsert_node_config(f.id, "extract", cfg, operator="self-heal")
        return True

    def migrate_ask_user_to_catalog(self) -> bool:
        """自愈：旧 ask_user 配置（templates_source=requirement_rules 的 rebuttal/workload 思路）
        → 目录驱动引导配置（mode=catalog）。幂等：已是 catalog 则不动；保留用户已改的新字段。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return False
        n = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id,
            ReasoningNodeConfig.node_key == "ask_user",
        ).first()
        try:
            old = json.loads(n.config) if n and n.config else {}
        except Exception:
            old = {}
        if old.get("mode") == "catalog":
            return False
        default_cfg = dict(_default_node_configs().get("ask_user") or {})
        cfg = dict(default_cfg)
        # 保留用户已填的新字段（如自定义 reply_format），丢弃旧的 templates_source
        cfg.update({k: v for k, v in old.items() if k != "templates_source" and v is not None})
        cfg["mode"] = "catalog"
        self.upsert_node_config(f.id, "ask_user", cfg, operator="self-heal")
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
            name="默认推理流", version=1, status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=True, description="开箱默认（=当前硬编码推理流）",
            created_at=now, updated_at=now, created_by="seed", updated_by="seed",
        )
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        for node_key, cfg in _default_node_configs().items():
            self.session.add(ReasoningNodeConfig(
                flow_id=f.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="seed",
            ))
        self.session.commit()
        return f.to_dict()

    def migrate_v1_to_v2_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否还是 v1 线性图（无 clarity_check 节点）。
        是则建 v2 新版本（v3 图 + 新节点 config），迁移用户改过的旧节点 config，激活新版。
        已是 v2+（含 clarity_check）则不迁移。开发/已部署环境重启即自动升级。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "clarity_check" in node_ids:
            return None  # 已是 v2+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v2（需求明确度判定）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v2：加 clarity_check / cond_clarity / ask_user / budget_check",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()  # 拿 new_flow.id

        # 旧节点 config 用户可能改过，迁移保留；新节点（clarity_check/cond_clarity/ask_user/budget_check）用默认
        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"clarity_check", "cond_clarity", "ask_user", "budget_check"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def migrate_v3_scene_analysis_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否缺 scene_analysis 节点（v3 场景分析）。

        缺则建 v4 新版本（新图：cond_clarity(false)→scene_analysis→cond_scene→select_baseline，
        cond_scene(false)→ask_user 反问场景），复制旧节点 config、新节点用默认，激活新版。
        已是 v3+（含 scene_analysis）则不迁移。开发/已部署环境重启即自动升级。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "scene_analysis" in node_ids:
            return None  # 已是 v3+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v4（场景分析）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v4：加 scene_analysis（场景分析）+ cond_scene（场景分支）",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()  # 拿 new_flow.id

        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"scene_analysis", "cond_scene"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            # select_baseline：旧配置可能被调成 3，会截断「多机型都推荐」（R20 裸 8 卡要
            # 同时出 ESA/ZSA 双机型）→ 迁移时对齐 MAX_PLANS（可在画布再调小）
            if node_key == "select_baseline":
                from app.api.candidate_search import MAX_PLANS as _MAX_PLANS
                _sb = dict(cfg)
                if int(_sb.get("max_plans") or 0) < _MAX_PLANS:
                    _sb["max_plans"] = _MAX_PLANS
                    cfg = _sb
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def migrate_v5_normalize_input_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否缺 normalize_input 节点（v5 需求输入规范化）。

        缺则建 v5 新版本（新图：normalize_input→extract→…），复制旧节点 config、
        新节点用默认，激活新版。已是 v5+（含 normalize_input）则不迁移。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "normalize_input" in node_ids:
            return None  # 已是 v5+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v5（需求输入规范化）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v5：加 normalize_input（需求输入规范化：格式归一/噪音过滤）",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()

        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"normalize_input"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def migrate_v6_llm_understand_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否缺 llm_understand / slot_validate 节点（v6 LLM 主理解）。

        缺则建 v6 新版本（新图：normalize_input→extract→llm_understand→slot_validate→clarity_check…），
        复制旧节点 config、新节点用默认（默认关，不拖慢流程），激活新版。
        已是 v6+（含 llm_understand）则不迁移。开发/已部署环境重启即自动升级。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "llm_understand" in node_ids:
            return None  # 已是 v6+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v6（LLM 主理解）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v6：加 llm_understand（LLM 主理解节点，默认关）+ slot_validate（槽位语义校验）",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()  # 拿 new_flow.id

        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"llm_understand", "slot_validate"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def migrate_v7_confirm_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否缺 confirm 节点（v7 LLM 确认面板）。

        缺则建 v7 新版本（新图：slot_validate→confirm→clarity_check…），复制旧节点 config、
        新节点用默认，激活新版。已是 v7+（含 confirm）则不迁移。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "confirm" in node_ids:
            return None  # 已是 v7+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v7（LLM 确认面板）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v7：加 confirm（LLM 确认面板：冲突/低置信度默认采纳、高亮可改）",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()

        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"confirm"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def migrate_v8_llm_audit_if_needed(self) -> Optional[dict]:
        """检测 active flow 是否缺 llm_audit 节点（v8 LLM 方案校对）。

        缺则建 v8 新版本（新图：budget_check→llm_audit→review），复制旧节点 config、
        新节点用默认（默认关），激活新版。已是 v8+（含 llm_audit）则不迁移。
        """
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).first()
        if not f:
            return None
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        node_ids = {n.get("id") for n in graph.get("nodes") or []}
        if "llm_audit" in node_ids:
            return None  # 已是 v8+

        now = datetime.now().isoformat()
        new_flow = ReasoningFlow(
            name="默认推理流 v8（LLM 方案校对）",
            version=(f.version or 1) + 1,
            status="active",
            graph=json.dumps(DEFAULT_GRAPH, ensure_ascii=False),
            is_active=False,
            description="v8：加 llm_audit（LLM 方案校对：bom_cases few-shot 意图级校对，默认关）",
            created_at=now, updated_at=now, created_by="migrate", updated_by="migrate",
        )
        self.session.add(new_flow)
        self.session.flush()

        old_cfgs = {n.node_key: (json.loads(n.config) if n.config else {}) for n in
                    self.session.query(ReasoningNodeConfig).filter(ReasoningNodeConfig.flow_id == f.id).all()}
        _NEW_NODES = {"llm_audit"}
        for node_key, default_cfg in _default_node_configs().items():
            cfg = old_cfgs.get(node_key, default_cfg) if node_key not in _NEW_NODES else default_cfg
            self.session.add(ReasoningNodeConfig(
                flow_id=new_flow.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="migrate",
            ))
        f.is_active = False
        new_flow.is_active = True
        self.session.commit()
        self.session.refresh(new_flow)
        return new_flow.to_dict()

    def close(self):
        self.session.close()
