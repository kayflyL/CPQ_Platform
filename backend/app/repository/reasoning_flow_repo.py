"""Repository for rules.reasoning_flow + reasoning_node_config。

仿 strategy_repo 模式。提供 active 流读取、图/节点 config upsert、版本切换、默认 seed。
延迟 import requirement_intel_service / candidate_search 的模块常量（避免循环 import）。
"""
import json
from copy import deepcopy
from datetime import datetime
from typing import Optional, List
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.reasoning_flow import ReasoningFlow, ReasoningNodeConfig


GENERIC_NODE_TYPES = {
    "agent", "output", "input"
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


def _node_defaults_for(skill_key: Optional[str] = None) -> dict:
    """按 skill_key 取节点默认契约（DB 源：rules.reasoning_node_default，仅 DB）。"""
    from app.services import reasoning_node_contract
    return reasoning_node_contract.node_defaults(skill_key or "requirement_analysis")


def _requirement_analysis_node_configs() -> dict:
    """需求分析 Skill 的默认节点契约（DB 源：rules.reasoning_node_default，仅 DB）。"""
    return _node_defaults_for("requirement_analysis")

def _normalize_node_tool_names(cfg: dict) -> dict:
    """节点生效配置里工具名归一（旧名→现行名，剔除退役项）。幂等。"""
    if not isinstance(cfg, dict):
        return cfg
    raw = cfg.get("enabled_tools")
    if isinstance(raw, list):
        from ..services.tool_names import normalize_tool_ids
        cfg = dict(cfg)
        cfg["enabled_tools"] = normalize_tool_ids(raw)
    return cfg


def _merge_config(base: dict, override: dict) -> dict:
    """深合并：以默认值为底，用覆盖值（非空）覆盖；用于「默认契约 + 增量」合成生效配置。"""
    out = deepcopy(base or {})
    for k, v in (override or {}).items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_config(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def compute_tool_usage(flow_snapshots: list) -> dict:
    """tool_name → 引用它的节点标签（聚合全部活跃流的生效工具集）。

    生效集与运行时同一合成口径：默认契约 + 增量 + 机制保底
    （skill_plan_runtime.effective_node_tools），绝不另写一份清单。
    flow_snapshots 每项 = {"skill_key": str, "graph": dict, "node_deltas": {node_key: cfg}}。
    """
    from app.services.capability_spec import SPECS
    from app.services.skill_plan_runtime import effective_node_tools
    usage: dict[str, set] = {}
    for snap in flow_snapshots or []:
        defaults = _node_defaults_for(snap.get("skill_key"))
        g = snap.get("graph") or {}
        deltas = snap.get("node_deltas") or {}
        for node in (g.get("nodes") or []):
            key = str(node.get("id") or node.get("type") or "").strip()
            if not key:
                continue
            cfg = _normalize_node_tool_names(
                _merge_config(defaults.get(key) or {}, deltas.get(key) or {}))
            base = key[: key.rindex("_")] if "_" in key else key
            spec = SPECS.get(key) or SPECS.get(base)
            label = spec.label if spec else str(node.get("label") or key)
            for t in effective_node_tools(key, cfg):
                usage.setdefault(t, set()).add(label)
    return {t: sorted(labels) for t, labels in sorted(usage.items())}


def _legacy_node_keys(node_key: str) -> list:
    """节点配置里应被清掉的遗留键（旧一次性节点级提示词/决策字段）。"""
    if node_key == "agent_fill":
        return ["prompt", "system_prompt", "user_prompt_template"]
    if node_key == "model_reason":
        return ["selection_mode", "grounding_tool", "grounding_result_key", "choice_id_pattern", "choice_fields"]
    if node_key == "kp_reason":
        return ["user_prompt_template", "proposal_enabled", "proposal_schema", "proposal_mapping"]
    return []


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
    out = {"nodes": nodes, "edges": edges}
    # flow 级字段透传（SkillStudio 左栏任务规则；画布整存不丢）
    if isinstance(g.get("manual_rules"), str):
        out["manual_rules"] = g["manual_rules"]
    return out


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
        delta_map = {n.node_key: (json.loads(n.config) if n.config else {}) for n in nodes}

        d = f.to_dict()
        g = _normalize_graph(d.get("graph") or {"nodes": [], "edges": []})
        d["graph"] = g
        # 生效值 = 默认契约（DB reasoning_node_default）+ 增量（存量只存覆盖字段）
        defaults = _node_defaults_for(f.skill_key or f.name)
        effective = {}
        for node in g.get("nodes") or []:
            key = node.get("id") or node.get("type")
            if not key:
                continue
            effective[key] = _normalize_node_tool_names(_merge_config(defaults.get(key) or {}, delta_map.get(key, {})))
        d["node_configs"] = effective
        return d

    def tool_usage_map(self) -> dict:
        """活跃流的 工具→引用节点 聚合（AI 工具目录卡片「被引用」徽标数据源）。"""
        flows = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True).all()
        snaps = []
        for f in flows:
            rows = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id
            ).all()
            try:
                g = json.loads(f.graph) if isinstance(f.graph, str) else (f.graph or {})
            except Exception:
                g = {}
            snaps.append({
                "skill_key": f.skill_key or f.name or "",
                "graph": g if isinstance(g, dict) else {},
                "node_deltas": {n.node_key: (json.loads(n.config) if n.config else {}) for n in rows},
            })
        return compute_tool_usage(snaps)

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

    def update_manual_rules(self, flow_id: int, rules: str, operator: str = "system") -> Optional[dict]:
        """更新 flow 级任务规则（graph.manual_rules）。只动这一个键，不升版本、
        不走画布归一——规则是文字微调，不该让画布版本号抖动。"""
        f = self.session.query(ReasoningFlow).filter(ReasoningFlow.id == flow_id).first()
        if not f:
            return None
        try:
            g = json.loads(f.graph or "{}")
        except Exception:
            g = {}
        g = dict(g) if isinstance(g, dict) else {}
        if str(rules).strip():
            g["manual_rules"] = str(rules)
        else:
            g.pop("manual_rules", None)
        f.graph = json.dumps(g, ensure_ascii=False)
        f.updated_at = datetime.now().isoformat()
        f.updated_by = operator
        self.session.commit()
        self.session.refresh(f)
        return f.to_dict()

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
        """把存量 requirement_analysis 节点配置收敛为「增量」（相对 rules.reasoning_node_default）。

        只处理主链 canonical 节点；删主链外旧行；缺行补空增量 {}；已有行清遗留键
        并用 override_only 剥掉等于默认值的字段落回增量。幂等，重复跑无副作用。
        生效值由 get_active_flow 用「默认契约 + 增量」合成。
        """
        from app.services import reasoning_node_contract
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        if flow_id is not None:
            query = query.filter(ReasoningFlow.id == flow_id)
        f = query.first()
        if not f:
            return 0
        if (f.skill_key or f.name or "requirement_analysis") != "requirement_analysis":
            return 0
        defaults = reasoning_node_contract.node_defaults("requirement_analysis")
        if not defaults:
            return 0
        canonical = ["input", "agent_fill", "model_reason", "kp_reason", "compose", "output"]
        now = datetime.now().isoformat()
        changed = 0

        # 删主链外旧配置行
        for n in self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all():
            if n.node_key not in canonical:
                self.session.delete(n)
                changed += 1
        if changed:
            self.session.commit()

        for node_key in canonical:
            if node_key not in defaults:
                continue
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if not n:
                self.upsert_node_config(f.id, node_key, {}, operator="self-heal")
                changed += 1
                continue
            try:
                cfg = json.loads(n.config) if n.config else {}
            except Exception:
                cfg = {}
            dirty = False
            for k in _legacy_node_keys(node_key):
                if k in cfg:
                    cfg.pop(k, None)
                    dirty = True
            delta = reasoning_node_contract.override_only(node_key, cfg)
            if dirty or delta != cfg:
                n.config = json.dumps(delta, ensure_ascii=False)
                n.version = (n.version or 1) + 1
                n.updated_at = now
                n.updated_by = "self-heal"
                changed += 1
        self.session.commit()
        return changed

    def migrate_legacy_tool_names(self) -> int:
        """把存量节点配置里的旧工具名就地改写为现行名（幂等启动迁移）。

        覆盖两张表：reasoning_node_default（作者基准）与 reasoning_node_config（增量覆盖）。
        只改 enabled_tools，其它键不动；改完才写回并 bump version。返回改动行数。
        """
        from app.services.tool_names import normalize_tool_ids
        now = datetime.now().isoformat()
        changed = 0

        def _normalize_row(obj, attr: str):
            nonlocal changed
            try:
                cfg = json.loads(getattr(obj, attr)) if getattr(obj, attr) else {}
            except Exception:
                cfg = {}
            if not isinstance(cfg, dict):
                return
            raw = cfg.get("enabled_tools")
            if not isinstance(raw, list):
                return
            cur = [str(x).strip() for x in raw if str(x).strip()]
            norm = normalize_tool_ids(cur)
            if norm == cur:
                return
            cfg["enabled_tools"] = norm
            setattr(obj, attr, json.dumps(cfg, ensure_ascii=False))
            obj.version = (obj.version or 1) + 1
            obj.updated_at = now
            obj.updated_by = "self-heal"
            changed += 1

        from app.models.skill_config import ReasoningNodeDefault
        for d in self.session.query(ReasoningNodeDefault).all():
            _normalize_row(d, "config")
        for n in self.session.query(ReasoningNodeConfig).all():
            _normalize_row(n, "config")
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
                        "enabled_tools": ["query_data"],
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
            _store_cfg = {} if skill_key == "requirement_analysis" else (cfg or {})
            self.session.add(ReasoningNodeConfig(
                flow_id=flow.id,
                node_key=str(node_key),
                config=json.dumps(_store_cfg, ensure_ascii=False),
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
                config=json.dumps({}, ensure_ascii=False),
                version=1, updated_at=now, updated_by="seed",
            ))
        self.session.commit()
        return f.to_dict()


    def close(self):
        self.session.close()
