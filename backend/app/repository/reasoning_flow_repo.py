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
        {"id": "agent_fill", "type": "agent_fill", "label": "智能对话填表 Agent", "position": {"x": 280, "y": 200}},
        {"id": "model_reason", "type": "model_reason", "label": "机型选型", "position": {"x": 580, "y": 200}},
        {"id": "kp_reason", "type": "kp_reason", "label": "配件选型", "position": {"x": 860, "y": 200}},
        {"id": "compose", "type": "compose", "label": "方案组装·BOM", "position": {"x": 1140, "y": 200}},
        {"id": "output", "type": "output", "label": "输出·BOM方案草稿", "position": {"x": 1420, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "agent_fill"},
        {"id": "e2", "source": "agent_fill", "target": "model_reason"},
        {"id": "e3", "source": "model_reason", "target": "kp_reason"},
        {"id": "e4", "source": "kp_reason", "target": "compose"},
        {"id": "e5", "source": "compose", "target": "output"},
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
    """需求分析 Skill 的默认节点契约，只保留真实业务链：输入 → 线索登记 → 方案配置 → 输出。"""
    return {
        "input": {
            "description": "接收客户自然语言需求与商机上下文",
            "deterministic": True,
        },
        "agent_fill": {
            "description": "会对话、会查目录确认在售/系列、边答边填线索登记表；信息不足自然反问，一个回合可批量填多个槽；机型与配件的最终选型交给下游节点",
            "data_sources": ["server_catalog", "demand_analysis_docs"],
            "rule_types": ["platform_series_map", "category_alias", "workload_map", "compliance_map", "gpu_form_map", "type_package"],
            "conflict_strategy": "auto_resolve",
            "enabled_tools": ["list_server_types", "list_server_models", "get_server_model"],
        },
        "model_reason": {
            "description": "按线索登记字段推荐或智能选配在售机型骨架",
            "selection_mode": "recommend",
            "grounding_tool": "select_models",
            "grounding_result_key": "candidates",
            "choice_id_pattern": "id=(\d+)",
            "choice_fields": ["config_id", "server_model_id", "id"],
            "rule_types": ["fallback_order", "gpu_form_map", "compliance_map", "type_package"],
        },
        "kp_reason": {
            "description": "按线索登记字段选择关键配件",
            "proposal_enabled": True,
            "proposal_schema": {},
            "user_prompt_template": "",
            "proposal_mapping": {},
            "reason_template": "配件规划：已确认 {{items}}",
            "rule_types": ["type_package", "category_alias", "spec_rule", "cpu_mem_generation", "capacity_match", "raid_level_map", "compliance_map", "workload_map"],
        },
        "compose": {
            "description": "按真实 BOM 模板组装 bom_scheme.configs",
            "kp_source": "per_baseline",
            "psu_override_enabled": True,
            "psu_wattage_source": "ext.psu_signal.wattage",
            "psu_qty_source": "ext.psu_signal.qty",
            "deterministic": True,
        },
        "output": {
            "description": "写回真实 requirement + bom_scheme，并交付给 AI Office/商机详情页",
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
        """自愈：为 agent_fill 补齐可编辑职责文案与子任务提示词。

        只补缺失字段，不覆盖用户已保存的 enabled/system_prompt/label 等值。
        保证旧 active flow 打开抽屉时也能看到完整默认提示词，而不是前端另写一份硬编码。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        if flow_id is not None:
            query = query.filter(ReasoningFlow.id == flow_id)
        f = query.first()
        if not f:
            return 0
        defaults = _requirement_analysis_node_configs()
        changed = 0

        # 只保留主链节点配置；其余不在主链的旧键直接删除，避免干扰后续接管与回显。
        canonical = {"input", "agent_fill", "model_reason", "kp_reason", "compose", "output"}
        for n in self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all():
            if n.node_key not in canonical:
                self.session.delete(n)
                changed += 1
        if changed:
            self.session.commit()

        for node_key in ("input", "agent_fill", "model_reason", "kp_reason", "compose", "output"):
            default = defaults.get(node_key) or {}
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if not n:
                if node_key == "agent_fill":
                    # 画布已收敛到 agent_fill 但 DB 无配置行：补建默认配置并回填提示词，
                    # 保证抽屉打开即回显默认 system_prompt。
                    from app.services.prompt_store import merge_node_prompt
                    cfg = merge_node_prompt("agent_fill", dict(default))
                    self.upsert_node_config(f.id, node_key, cfg, operator="self-heal")
                    changed += 1
                continue
            try:
                cfg = json.loads(n.config) if n.config else {}
            except Exception:
                cfg = {}
            dirty = False

            if node_key == "agent_fill":
                if not cfg.get("description") and default.get("description"):
                    cfg["description"] = default["description"]
                    dirty = True

            if node_key in ("agent_fill", "model_reason", "kp_reason"):
                if not cfg.get("rule_types") and default.get("rule_types"):
                    cfg["rule_types"] = list(default["rule_types"])
                    dirty = True

            if node_key == "model_reason":
                for field in ("grounding_tool", "grounding_result_key",
                              "choice_id_pattern"):
                    if not cfg.get(field) and default.get(field):
                        cfg[field] = default[field]
                        dirty = True
                if not cfg.get("choice_fields") and default.get("choice_fields"):
                    cfg["choice_fields"] = list(default["choice_fields"])
                    dirty = True

            if node_key == "kp_reason":
                for field in ("proposal_enabled",):
                    if field not in cfg and field in default:
                        cfg[field] = bool(default[field])
                        dirty = True
                for field in ("proposal_schema", "proposal_mapping"):
                    if not cfg.get(field) and default.get(field):
                        cfg[field] = dict(default[field])
                        dirty = True
                for field in ("user_prompt_template", "reason_template"):
                    if not cfg.get(field) and default.get(field):
                        cfg[field] = default[field]
                        dirty = True
                for field in ("temperature", "timeout", "max_attempts"):
                    if cfg.get(field) is None and default.get(field) is not None:
                        cfg[field] = default[field]
                        dirty = True

            if node_key == "compose":
                for field in ("kp_source", "psu_wattage_source", "psu_qty_source"):
                    if not cfg.get(field) and default.get(field):
                        cfg[field] = default[field]
                        dirty = True
                if "psu_override_enabled" not in cfg and "psu_override_enabled" in default:
                    cfg["psu_override_enabled"] = bool(default["psu_override_enabled"])
                    dirty = True

            if node_key == "agent_fill":
                for legacy_key in ("system_prompt", "user_prompt_template", "output_schema",
                                   "option_scopes", "fallback_forms", "fallback_series",
                                   "ask_skill_key", "show_why", "max_rounds",
                                   "strategy", "max_ask_rounds", "target", "entry_points"):
                    if legacy_key in cfg:
                        cfg.pop(legacy_key)
                        dirty = True
                if not cfg.get("data_sources") and default.get("data_sources"):
                    cfg["data_sources"] = list(default["data_sources"])
                    dirty = True
                if not cfg.get("rule_types") and default.get("rule_types"):
                    cfg["rule_types"] = list(default["rule_types"])
                    dirty = True
                if not cfg.get("enabled_tools") and default.get("enabled_tools"):
                    cfg["enabled_tools"] = list(default["enabled_tools"])
                    dirty = True
                # 方案A(2026-08)：agent_fill 只做理解/查证/填表；把 select_models/pick_kp_parts
                # 两个选型/配件决策工具交回 model_reason/kp_reason，避免 Agent 一把梭定方案。
                _dtools = list(cfg.get("enabled_tools") or [])
                _norm = [t for t in _dtools if t not in ("select_models", "pick_kp_parts")]
                for _t in (default.get("enabled_tools") or []):
                    if _t not in _norm:
                        _norm.append(_t)
                if _norm != _dtools:
                    cfg["enabled_tools"] = _norm
                    dirty = True


            if dirty:
                self.upsert_node_config(f.id, node_key, cfg, operator="self-heal")
                changed += 1
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
                        "max_iterations": 6,
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
