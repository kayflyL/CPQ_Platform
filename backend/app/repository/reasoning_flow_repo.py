"""Repository for rules.reasoning_flow + reasoning_node_config。

仿 strategy_repo 模式。提供 active 流读取、图/节点 config upsert、版本切换、默认 seed。
延迟 import requirement_intel_service / candidate_search 的模块常量（避免循环 import）。
"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.reasoning_flow import ReasoningFlow, ReasoningNodeConfig


GENERIC_NODE_TYPES = {
    "agent", "rule", "transform", "branch", "assemble", "output", "orchestrator", "input"
}


# 默认图结构 v13（单路能力链，2026-08 重构·最终形态）—— 执行走 Graph Orchestrator。
# 需求分析默认图已对齐商机详情页真实业务四步：
# input（需求/商机上下文）→ agent_fill（智能对话填表 Agent）→ model_reason/kp_reason/compose（方案配置）→ output（BOM 方案草稿）。
DEFAULT_REQUIREMENT_ANALYSIS_GRAPH = {
    "nodes": [
        {"id": "input", "type": "input", "label": "输入", "position": {"x": 0, "y": 200}},
        {"id": "need_analysis", "type": "agent", "label": "需求分析 Agent", "position": {"x": 300, "y": 200}},
        {"id": "model_choice", "type": "agent", "label": "机型选型 Agent", "position": {"x": 600, "y": 200}},
        {"id": "parts_proposal", "type": "agent", "label": "配件选配 Agent", "position": {"x": 900, "y": 200}},
        {"id": "bom_assemble", "type": "agent", "label": "BOM 组装 Agent", "position": {"x": 1200, "y": 200}},
        {"id": "output", "type": "output", "label": "输出·BOM方案草稿", "position": {"x": 1500, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "need_analysis"},
        {"id": "e2", "source": "need_analysis", "target": "model_choice"},
        {"id": "e3", "source": "model_choice", "target": "parts_proposal"},
        {"id": "e4", "source": "parts_proposal", "target": "bom_assemble"},
        {"id": "e5", "source": "bom_assemble", "target": "output"},
    ],
}


DEFAULT_GRAPH_TREND = {
    "nodes": [
        {"id": "input", "type": "input", "label": "输入", "position": {"x": 0, "y": 200}},
        {"id": "agent", "type": "agent", "label": "趋势分析智能体", "position": {"x": 300, "y": 200}},
        {"id": "output", "type": "output", "label": "输出", "position": {"x": 600, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "output"},
    ],
}


DEFAULT_GENERIC_GRAPH = {
    "nodes": [
        {"id": "input", "type": "input", "label": "输入", "position": {"x": 0, "y": 200}},
        {"id": "agent", "type": "agent", "label": "技能智能体", "position": {"x": 300, "y": 200}},
        {"id": "output", "type": "output", "label": "输出", "position": {"x": 600, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "output"},
    ],
}


def _requirement_analysis_node_configs() -> dict:
    """需求分析 Skill 默认节点契约（AI 优先 5 节点链）。

    设计：AI 只做理解+编排，事实（目录/价格/兼容/BOM）全部由工具从规则库与目录读取；
    代码里不写死任何价格、兼容表、配件词表。每个 agent 节点用 enabled_tools 收窄工具，
    用 context_map 把上游结构化结果注入，用 result_key/result_mapping/action 写回 ctx。
    """
    return {
        "input": {
            "description": "接收客户自然语言需求与商机上下文",
            "deterministic": True,
        },
        "need_analysis": {
            "description": "智能体理解需求→读规则目录→输出结构化需求槽位（server_type/form/series/gpu/raid 等）",
            "enabled_tools": ["load_requirement_rules", "list_server_types", "list_server_models"],
            "system_prompt": (
                "你是【需求分析 Agent】。把客户自然语言需求转成结构化槽位，供后续选型/选配/报价使用。\n"
                "铁律：只做理解与编排，不记忆价格、兼容、BOM。凡涉及目录、系列、形态、配件、类型的事实，"
                "一律调用工具获取；不确定就调用工具确认，绝不编造。\n"
                "工具：load_requirement_rules（读需求规则/别名）、list_server_types/list_server_models（在售目录）。\n"
                "先调用 load_requirement_rules 读规则，再按规则把需求规范化。\n"
                "最终必须用 final 动作，且 answer 字段是如下 JSON 对象（不要多余文字），形如：\n"
                '{"requirement": {"server_type_name":"通用服务器","server_type":"通用","form":"2U","series":"",'
                '"gpu_count":2,"raid_level":"","nic_speed":"","psu_signal":{},"purchase_qty":1,"gpu_groups":[],'
                '"scope":"","usage":""}, "summary":"一句话需求要点"}'
            ),
            "result_key": "need_analysis",
            "final_only": True,
            "final_only_contract": ("直接给出需求槽位 JSON，键名必须按下表，不得改名："
                                     '{"requirement": {"server_type_name":"服务器类型全名","server_type":"通用|AI|存储|边缘|GPU","form":"1U|2U|4U|8U",'
                                     '"series":"产品系列(可空)","gpu_count":0,"raid_level":"","nic_speed":"","purchase_qty":1,'
                                     '"gpu_groups":[{"kind":"GPU","qty":0}],"scope":"","usage":"用途简要"},'
                                     '"summary":"一句话需求要点"}。server_type_name/form/gpu_count 必须从需求里精确提取，无法确定就留空，禁止臆造。'),
            "pre_tools": [{"tool": "load_requirement_rules", "args": {}}],
            "result_mapping": {
                "requirement": "requirement",
                "ext": "requirement",
                "normalized_text": "summary",
            },
            "context_map": [],
            "max_iterations": 4,
            "allowed_effects": [],
            "rule_types": ["category_alias", "platform_series_map", "type_alias", "gpu_form_map",
                           "raid_level_map", "cpu_mem_generation", "workload_map"],
        },
        "model_choice": {
            "description": "智能体按需求从目录筛机型并用 validate_compat 校验；用户可选自配并收到机型卡片",
            "enabled_tools": ["select_models", "validate_compat", "load_requirement_rules"],
            "system_prompt": (
                "你是【机型选型 Agent】。上游已给需求槽位（见“需求槽位”）。任务：调用 select_models 从目录筛出候选机型，"
                "再调用 validate_compat 校验候选与需求是否可行，给出推荐。\n"
                "铁律：不背价格/兼容/目录，一切以工具返回为准；无匹配就如实说明并建议放宽。\n"
                "工具：select_models（按 server_type/form/series/usage 筛）、validate_compat（校验）。\n"
                "若用户明确表示“自己配/不要推荐/我要自己选”，则 action 置为 self_config，"
                "把候选机型放入 candidates，到此为止（系统会推送机型卡片让你进入自配页）。\n"
                "最终必须用 final 动作，且 answer 字段是如下 JSON 对象：\n"
                '{"action":"recommend|self_config","candidates":[...工具返回candidates...],'
                '"recommended":<推荐项，含baseline>,"recommended_index":0,"reason":"推荐理由",'
                '"baseline":<推荐项的baseline>}'
            ),
            "result_key": "model_choice",
            "final_only": True,
            "final_only_contract": ("直接给出机型决策 JSON：{\"action\":\"recommend|self_config\",\"candidates\":[select_models候选digest],"
                                     "\"recommended\":<建议候选含baseline>,\"baseline\":<建议候选的baseline>,\"reason\":\"推荐理由\"}。"
                                     "用户表示自配时 action=self_config。"),
            "pre_tools": [{"tool": "select_models", "args": {"server_type_name": "req.server_type_name", "form": "req.form", "series": "req.series", "usage": "req.usage", "limit": 6}}],
            "result_mapping": {
                "candidates": "candidates",
                "baselines": "candidates",
                "recommended": "recommended",
                "baseline": "baseline",
                "recommended_index": "recommended_index",
                "model_choice_reason": "reason",
                "action": "action",
                "flow_exit": "flow_exit",
            },
            "context_map": [{"key": "requirement", "label": "需求槽位"}],
            "max_iterations": 4,
            "allowed_effects": ["self_config"],
        },
        "parts_proposal": {
            "description": "智能体按需求+已选机型从配件库挑配件，并校验兼容，输出 parts_proposal 契约",
            "enabled_tools": ["select_parts", "validate_compat"],
            "system_prompt": (
                "你是【配件选配 Agent】。已给需求槽位与已选机型（见“需求槽位/已选机型”）。任务："
                "调用 select_parts 按类目挑配件，再调用 validate_compat（用已选机型 baseline）校验兼容，"
                "必要时换件重选。\n"
                "铁律：不背配件型号/价格，全部以 select_parts 返回为准；无法命中就用工具给的代表件，并在 summary 说明。\n"
                "最终必须用 final 动作，且 answer 字段是如下 JSON 对象：\n"
                '{"baseline":<上游baseline>,"by_category":{"CPU":[...],"Memory":[...]},'
                '"parts":[...select_parts返回parts...],"summary":"配件规划要点"}'
            ),
            "result_key": "parts_proposal",
            "final_only": True,
            "final_only_contract": ("直接给出配件契约 JSON：{\"baseline\":<已选机型baseline>,\"by_category\":{...},\"parts\":[select_parts返回parts...],"
                                     "\"summary\":\"配件规划要点\"}。baseline 取上游已选机型，不要改价格/型号。"),
            "pre_tools": [{"tool": "select_parts", "args": {"categories": ["CPU", "Memory", "HDD/SSD", "GPU", "NIC", "RAID"], "server_type_name": "req.server_type_name"}}],
            "result_mapping": {
                "parts": "parts",
                "kp_parts": "parts",
                "by_category": "by_category",
                "baseline": "baseline",
                "part_summary": "summary",
            },
            "context_map": [{"key": "requirement", "label": "需求槽位"}, {"key": "baseline", "label": "已选机型"}],
            "max_iterations": 4,
            "allowed_effects": [],
        },
        "bom_assemble": {
            "description": "智能体用 validate_compat+compute_price 校验并算价，触发确定性 build_bom 产出整机方案",
            "enabled_tools": ["validate_compat", "compute_price", "select_parts", "select_models"],
            "system_prompt": (
                "你是【BOM 组装 Agent】。已给需求槽位、已选机型、配件清单。任务：调用 validate_compat 确认整体可行，"
                "调用 compute_price 取得真实成本，然后输出 action=build_bom 触发确定性 BOM 组装。\n"
                "铁律：不手拼 BOM、不估成本；成本/兼容事实全部来自工具返回，最终方案由系统按真实 BOM 模板组装。\n"
                "最终必须用 final 动作，且 answer 字段是如下 JSON 对象：\n"
                '{"action":"build_bom","baseline":<已选机型baseline>,"parts":<配件清单>,'
                '"cost":<compute_price返回cost>,"summary":"方案要点"}'
            ),
            "result_key": "bom_scheme",
            "final_only": True,
            "final_only_contract": ("直接给出 BOM 组装 JSON：{\"action\":\"build_bom\",\"baseline\":<已选机型baseline>,\"parts\":<配件清单>,"
                                     "\"cost\":<compute_price返回cost>,\"summary\":\"方案要点\"}。cost 必须用工具返回值，禁止估算。"),
            "pre_tools": [
                {"tool": "validate_compat", "args": {"baseline": "ctx.baseline", "parts": "ctx.parts", "requirement": "ctx.requirement"}},
                {"tool": "compute_price", "args": {"baseline": "ctx.baseline", "parts": "ctx.parts"}},
            ],
            "result_mapping": {
                "baseline": "baseline",
                "parts": "parts",
                "bom_scheme": "bom_scheme",
                "requirement": "requirement",
                "ext": "requirement",
                "bom_cost": "cost",
                "bom_summary": "summary",
            },
            "context_map": [
                {"key": "requirement", "label": "需求槽位"},
                {"key": "baseline", "label": "已选机型"},
                {"key": "parts_proposal", "label": "配件选配"},
                {"key": "parts", "label": "配件清单"},
            ],
            "max_iterations": 4,
            "allowed_effects": ["build_bom"],
        },
        "output": {
            "description": "写回真实 requirement + bom_scheme，并交付 AI Office / 商机详情页",
            "output_kind": "bom_scheme_draft",
            "target": "bom_scheme",
            "payload_map": {"plans": "ctx.plans", "ext": "ctx.ext"},
            "actions": [],
            "deterministic": True,
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
        runtime = n.get("runtime") or (n.get("data") or {}).get("runtime")
        if not runtime and ntype not in GENERIC_NODE_TYPES:
            runtime = ntype
        label = n.get("label") or nid
        pos = n.get("position") or {"x": i * 300, "y": 200}
        nn: dict = {"id": nid, "type": ntype, "label": label, "position": pos}
        if runtime:
            nn["runtime"] = runtime
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


_PROMPT_NODE_TYPES = {"agent_fill", "kp_reason", "model_reason", "orchestrator"}


def _prompt_node_type(node_key: str) -> Optional[str]:
    """节点 id → 可回显提示词的节点类型（兼容后缀 id，如 agent_fill_2）。"""
    nk = str(node_key or "")
    if nk in _PROMPT_NODE_TYPES:
        return nk
    base = nk.rsplit("_", 1)[0]
    return base if base in _PROMPT_NODE_TYPES else None


class ReasoningFlowRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def get_active_flow(self, skill_key: Optional[str] = None) -> Optional[dict]:
        """取 active 流（含 graph + node_configs 按 node_key 索引）。无 active 返回 None。

        优先按正式 skill_key 字段匹配，再回退旧库 name == skill_key；不传则保持
        历史全局行为（优先 requirement_analysis，再回退首个 active）。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        if skill_key:
            f = query.filter(ReasoningFlow.skill_key == skill_key).first()
            if not f:
                f = query.filter(ReasoningFlow.name == skill_key).first()
        else:
            # 无 skill_key 时保持旧语义：优先 requirement_analysis，再回退首个 active。
            f = query.filter(ReasoningFlow.skill_key == "requirement_analysis").first()
            if not f:
                f = query.filter(ReasoningFlow.name == "requirement_analysis").first()
            if not f:
                f = query.first()
        if not f:
            return None
        self.self_heal_agent_node_configs(flow_id=f.id)
        nodes = self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all()
        cfg_map = {n.node_key: (json.loads(n.config) if n.config else {}) for n in nodes}
        # 提示词/话术不在 DB 里复制全量默认：读取时把 system_config.reasoning_prompts
        # 的默认值合入（只填空缺字段），前端抽屉回显生效值，用户编辑后仍以其覆盖子集为准。
        try:
            from app.services.prompt_store import merge_node_prompt
            for nk, cfg in list(cfg_map.items()):
                ptype = _prompt_node_type(nk)
                if ptype:
                    cfg_map[nk] = merge_node_prompt(ptype, cfg)
        except Exception:
            pass
        d = f.to_dict()
        d["graph"] = _normalize_graph(d.get("graph") or {"nodes": [], "edges": []})
        d["node_configs"] = cfg_map
        return d

    def active_is_current(self) -> bool:
        """active 流是否已是真实业务四步对齐图（含 output 节点）。

        防护 migrate 膨胀：active 已最新 → startup 跳过所有建流 migrate，绝不新建。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        f = query.filter(ReasoningFlow.skill_key == "requirement_analysis").first()
        if not f:
            f = query.filter(ReasoningFlow.name == "requirement_analysis").first()
        if not f:
            f = query.first()
        if not f:
            return False
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        active_ids = {n.get("id") for n in graph.get("nodes") or []}
        expected_ids = {n.get("id") for n in DEFAULT_REQUIREMENT_ANALYSIS_GRAPH.get("nodes") or []}
        return active_ids == expected_ids

    def migrate_requirement_analysis_to_business_graph(self, operator: str = "migrate") -> bool:
        """一次性把旧需求分析图重置为真实业务四步图，并重写节点配置。

        当前图节点与默认业务图完全一致时跳过；否则重置，避免旧节点持续污染执行链。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        f = query.filter(ReasoningFlow.skill_key == "requirement_analysis").first()
        if not f:
            f = query.filter(ReasoningFlow.name == "requirement_analysis").first()
        if not f:
            return False
        graph = _normalize_graph(json.loads(f.graph) if f.graph else {"nodes": [], "edges": []})
        active_ids = {n.get("id") for n in graph.get("nodes") or []}
        expected_ids = {n.get("id") for n in DEFAULT_REQUIREMENT_ANALYSIS_GRAPH.get("nodes") or []}
        default_nodes = {n.get("id"): n for n in DEFAULT_REQUIREMENT_ANALYSIS_GRAPH.get("nodes") or []}
        now = datetime.now().isoformat()
        label_dirty = False
        for node in graph.get("nodes") or []:
            nid = node.get("id")
            expected = default_nodes.get(nid)
            if not expected:
                continue
            current_label = str(node.get("label") or "").strip()
            if current_label and current_label != nid:
                continue
            expected_label = str(expected.get("label") or "").strip()
            if expected_label and current_label != expected_label:
                node["label"] = expected_label
                label_dirty = True
        if label_dirty:
            f.graph = json.dumps(graph, ensure_ascii=False)
            f.updated_at = now
            f.updated_by = operator
            self.session.commit()
        if active_ids == expected_ids:
            # 图已对齐但 node_configs 键未对齐（缺 agent_fill 或存在主链外旧键残留）
            # 时不可直接跳过，需交给自愈补齐/清理，避免抽屉回显空白。
            cfg_keys = {n.node_key for n in self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id
            ).all()}
            expected_cfg_keys = set(_requirement_analysis_node_configs().keys())
            if cfg_keys != expected_cfg_keys:
                self.self_heal_agent_node_configs(flow_id=f.id)
                return True
            return label_dirty

        f.name = "requirement_analysis"
        f.skill_key = "requirement_analysis"
        f.graph = json.dumps(DEFAULT_REQUIREMENT_ANALYSIS_GRAPH, ensure_ascii=False)
        f.version = (f.version or 1) + 1
        f.description = "真实业务四步对齐：input→agent_fill→model_reason→kp_reason→compose→output"
        f.updated_at = now
        f.updated_by = operator
        self.session.commit()

        for n in self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all():
            self.session.delete(n)
        self.session.commit()

        for node_key, cfg in _requirement_analysis_node_configs().items():
            self.session.add(ReasoningNodeConfig(
                flow_id=f.id,
                node_key=str(node_key),
                config=json.dumps(cfg or {}, ensure_ascii=False),
                version=1,
                updated_at=now,
                updated_by=operator,
            ))
        self.session.commit()
        return True

    def get(self, flow_id: int) -> Optional[dict]:
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        return f.to_dict() if f else None

    def list_versions(self, skill_key: Optional[str] = None) -> List[dict]:
        out = []
        query = self.session.query(ReasoningFlow).order_by(ReasoningFlow.id.desc())
        if skill_key:
            query = query.filter(or_(ReasoningFlow.skill_key == skill_key, ReasoningFlow.name == skill_key))
        for f in query.all():
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

    def update_node_label(self, flow_id: int, node_key: str, label: str,
                          operator: str = "system") -> Optional[dict]:
        """只更新 active 流图结构中某节点的 label，不触碰 node_config。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        try:
            raw_graph = json.loads(f.graph) if f.graph else {"nodes": [], "edges": []}
        except Exception:
            raw_graph = {"nodes": [], "edges": []}
        graph = _normalize_graph(raw_graph)
        target = next((n for n in graph.get("nodes") or [] if n.get("id") == node_key), None)
        if target is None:
            return None
        target["label"] = str(label or node_key)
        f.graph = json.dumps(graph, ensure_ascii=False)
        f.version = (f.version or 1) + 1
        f.updated_at = datetime.now().isoformat()
        f.updated_by = operator
        self.session.commit()
        self.session.refresh(f)
        return f.to_dict()

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


    def self_heal_agent_node_configs(self, flow_id: Optional[int] = None) -> int:
        """自愈节点配置：仅对 requirement_analysis 生效，主链集合从默认配置动态取。

        不再写死旧六节点集合；非 requirement_analysis 技能不做删除/新建，避免误伤。
        只补缺失字段，不覆盖用户已保存的 enabled/system_prompt/label 等值。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        if flow_id is not None:
            query = query.filter(ReasoningFlow.id == flow_id)
        f = query.first()
        if not f:
            return 0
        is_ra = str(f.skill_key or f.name or "") == "requirement_analysis"
        if not is_ra:
            return 0
        defaults = _requirement_analysis_node_configs()
        canonical = set(defaults.keys())
        changed = 0

        for n in self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all():
            if n.node_key not in canonical:
                self.session.delete(n)
                changed += 1
        if changed:
            self.session.commit()

        for node_key in canonical:
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if n:
                continue
            default = dict(defaults.get(node_key) or {})
            ptype = _prompt_node_type(node_key)
            if ptype:
                try:
                    from app.services.prompt_store import merge_node_prompt
                    default = merge_node_prompt(ptype, default)
                except Exception:
                    pass
            self.upsert_node_config(f.id, node_key, default, operator="self-heal")
            changed += 1

        for node_key in canonical:
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if not n:
                continue
            try:
                cfg = json.loads(n.config) if n.config else {}
            except Exception:
                cfg = {}
            default = defaults.get(node_key) or {}
            dirty = False
            for k, v in default.items():
                if k in ("description", "system_prompt"):
                    continue
                if isinstance(v, dict):
                    if isinstance(cfg.get(k), dict) and not cfg[k]:
                        cfg[k] = dict(v)
                        dirty = True
                    elif cfg.get(k) is None:
                        cfg[k] = dict(v)
                        dirty = True
                elif isinstance(v, list):
                    if cfg.get(k) in (None, []):
                        cfg[k] = list(v)
                        dirty = True
                else:
                    if cfg.get(k) is None:
                        cfg[k] = v
                        dirty = True
            if dirty:
                n.config = json.dumps(cfg, ensure_ascii=False)
                n.updated_at = datetime.now().isoformat()
                n.updated_by = "self-heal"
                changed += 1
        if changed:
            self.session.commit()
        return changed

    def activate(self, flow_id: int, operator: str = "system") -> Optional[dict]:
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        # 只停用同一技能下的 active 版本，不再把所有技能的 active 一起清掉。
        scope = f.skill_key or f.name
        for other in self.session.query(ReasoningFlow).filter(
            ReasoningFlow.is_active == True,
            or_(ReasoningFlow.skill_key == scope, ReasoningFlow.name == scope),
            ReasoningFlow.id != flow_id,
        ).all():
            other.is_active = False
        f.is_active = True
        f.status = "active"
        f.updated_at = datetime.now().isoformat()
        f.updated_by = operator
        self.session.commit()
        self.session.refresh(f)
        return f.to_dict()

    def deactivate_skill_flows(self, skill_key: str, operator: str = "system") -> int:
        """删除技能时软删对应工作流图：停止 active 并标记 deleted，避免留下孤儿图。"""
        rows = self.session.query(ReasoningFlow).filter(or_(
            ReasoningFlow.skill_key == skill_key,
            ReasoningFlow.name == skill_key,
        )).all()
        changed = 0
        now = datetime.now().isoformat()
        for row in rows:
            if row.is_active or row.status != "deleted":
                row.is_active = False
                row.status = "deleted"
                row.updated_at = now
                row.updated_by = operator
                changed += 1
        if changed:
            self.session.commit()
        return changed

    def ensure_skill_flow(
        self,
        skill_key: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        graph: Optional[dict] = None,
        node_configs: Optional[dict] = None,
    ) -> dict:
        """确保指定技能有一份可编辑、可执行的 active flow；没有则按技能类型种子化。"""
        f = self.session.query(ReasoningFlow).filter(or_(
            ReasoningFlow.skill_key == skill_key,
            ReasoningFlow.name == skill_key,
        )).order_by(ReasoningFlow.id.asc()).first()
        if f:
            if not f.skill_key:
                f.skill_key = skill_key
                self.session.commit()
            if not f.is_active:
                self.activate(f.id, operator="seed")
            if skill_key == "requirement_analysis":
                self.migrate_requirement_analysis_to_business_graph(operator="ensure")
            return self.get_active_flow(skill_key) or f.to_dict()

        # 历史库只有一个全局 active flow（需求分析），name 可能是中文旧名。把该旧 flow
        # 收编为 requirement_analysis，避免同名技能出现两份 active 图。
        if skill_key == "requirement_analysis":
            legacy = self.session.query(ReasoningFlow).filter(
                ReasoningFlow.is_active == True
            ).first()
            if legacy:
                legacy.name = skill_key
                legacy.skill_key = skill_key
                self.session.commit()
                self.session.refresh(legacy)
                self.migrate_requirement_analysis_to_business_graph(operator="ensure")
                return self.get_active_flow(skill_key) or legacy.to_dict()

        if graph is None:
            if skill_key == "requirement_analysis":
                graph = DEFAULT_REQUIREMENT_ANALYSIS_GRAPH
            elif skill_key == "trend_analysis":
                graph = DEFAULT_GRAPH_TREND
            else:
                graph = DEFAULT_GENERIC_GRAPH
        if node_configs is None:
            if skill_key == "requirement_analysis":
                node_configs = _requirement_analysis_node_configs()
            else:
                node_configs = {
                    "input": {},
                    "agent": {
                        "enabled_tools": ["query_cpq_data"],
                        "max_iterations": 4,
                        "system_prompt": "",
                        "rule_types": [],
                    },
                    "output": {
                        "template": "{{agent_result.answer}}",
                        "output_schema": {"answer": "string"},
                        "output_kind": "data_answer" if skill_key == "trend_analysis" else "generic",
                        "target": "conversation_reply" if skill_key == "trend_analysis" else "artifact",
                        "payload_map": {"answer": "ctx.agent_result.answer"} if skill_key == "trend_analysis" else {},
                        "actions": [],
                    },
                }
        now = datetime.now().isoformat()
        flow = ReasoningFlow(
            name=skill_key,
            skill_key=skill_key,
            version=1,
            status="active",
            graph=json.dumps(_normalize_graph(graph), ensure_ascii=False),
            is_active=True,
            description=description or name or skill_key,
            created_at=now,
            updated_at=now,
            created_by="seed",
            updated_by="seed",
        )
        self.session.add(flow)
        self.session.commit()
        self.session.refresh(flow)
        for node_key, cfg in (node_configs or {}).items():
            self.session.add(ReasoningNodeConfig(
                flow_id=flow.id,
                node_key=str(node_key),
                config=json.dumps(cfg or {}, ensure_ascii=False),
                version=1,
                updated_at=now,
                updated_by="seed",
            ))
        self.session.commit()
        return self.get_active_flow(skill_key) or flow.to_dict()

    def seed_default_if_empty(self) -> dict:
        """无任何 flow 时建 v1（= 当前硬编码），设 active。已有则返回首个。"""
        existing = self.session.query(ReasoningFlow).first()
        if existing:
            if not existing.skill_key:
                existing.skill_key = existing.name or "requirement_analysis"
                self.session.commit()
            return existing.to_dict()
        now = datetime.now().isoformat()
        f = ReasoningFlow(
            name="requirement_analysis", skill_key="requirement_analysis", version=1, status="active",
            graph=json.dumps(DEFAULT_REQUIREMENT_ANALYSIS_GRAPH, ensure_ascii=False),
            is_active=True, description="真实业务四步对齐：input→agent_fill→model_reason→kp_reason→compose→output",
            created_at=now, updated_at=now, created_by="seed", updated_by="seed",
        )
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        for node_key, cfg in _requirement_analysis_node_configs().items():
            self.session.add(ReasoningNodeConfig(
                flow_id=f.id, node_key=node_key,
                config=json.dumps(cfg, ensure_ascii=False),
                version=1, updated_at=now, updated_by="seed",
            ))
        self.session.commit()
        return f.to_dict()


    def close(self):
        self.session.close()
