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


# 默认图结构 v3（vue flow 兼容）：v2 基础上加 clarity_check → cond_clarity 分支（true→ask_user 反问 / false→正常选型）
# + compose 后 budget_check。⚠️ cond_clarity 的 false 边必须显式 source_handle="false"（executor 把缺省 handle 当 true）
DEFAULT_GRAPH = {
    "nodes": [
        {"id": "extract", "type": "extract", "label": "需求理解与关键词提取", "position": {"x": 0, "y": 200}},
        {"id": "clarity_check", "type": "clarity_check", "label": "需求明确度判定", "position": {"x": 300, "y": 200}},
        {"id": "cond_clarity", "type": "condition", "label": "明确度分支", "position": {"x": 600, "y": 200}},
        {"id": "ask_user", "type": "ask_user", "label": "反问补全信息", "position": {"x": 900, "y": 60}},
        {"id": "select_baseline", "type": "select_baseline", "label": "机型选型（基准配置）", "position": {"x": 900, "y": 340}},
        {"id": "match_kp", "type": "match_kp", "label": "配件匹配", "position": {"x": 1200, "y": 340}},
        {"id": "compose", "type": "compose", "label": "组合整机方案", "position": {"x": 1500, "y": 340}},
        {"id": "budget_check", "type": "budget_check", "label": "预算校验", "position": {"x": 1800, "y": 340}},
        {"id": "review", "type": "review", "label": "方案就绪", "position": {"x": 2100, "y": 340}},
    ],
    "edges": [
        {"id": "e1", "source": "extract", "target": "clarity_check"},
        {"id": "e2", "source": "clarity_check", "target": "cond_clarity"},
        {"id": "e3", "source": "cond_clarity", "target": "ask_user", "source_handle": "true"},
        {"id": "e4", "source": "cond_clarity", "target": "select_baseline", "source_handle": "false"},
        {"id": "e5", "source": "select_baseline", "target": "match_kp"},
        {"id": "e6", "source": "match_kp", "target": "compose"},
        {"id": "e7", "source": "compose", "target": "budget_check"},
        {"id": "e8", "source": "budget_check", "target": "review"},
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
    from app.api.candidate_search import CATEGORY_KP_ALIASES, MAX_PLANS, PER_KEYWORD_LIMIT
    return {
        "extract": {
            "keyword_limit": 12,
            "lexicons": [
                {
                    "id": "lex_kp", "name": "KP 配件词表", "kind": "kp",
                    "entries": [
                        {"key": "CPU", "triggers": ["cpu", "processor", "处理器", "epyc", "xeon", "至强", "intel", "amd"]},
                        {"key": "Memory", "triggers": ["memory", "ram", "内存", "ddr", "rdimm"]},
                        {"key": "HDD/SSD", "triggers": ["hdd", "ssd", "nvme", "硬盘", "磁盘", "sata", "u.2", "u.3"]},
                        {"key": "GPU", "triggers": ["gpu", "显卡", "图形卡", "rtx", "l40", "w7900", "a100", "h100", "4090", "5090", "涡轮卡", "涡轮"]},
                        {"key": "Raid card", "triggers": ["raid", "阵列卡", "mega", "brocade"]},
                        {"key": "Network(NIC) requirement", "triggers": ["nic", "网络", "网卡", "ethernet", "e810", "mlx", "connectx"]},
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
                        {"key": "Polaris", "triggers": ["polaris"]},
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
            ],
            "qty_multipliers": ["*", "×"],  # 结构化清单乘号（*N / ×N）
            "model_token_regex": r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$",  # 型号 token 正则（必含数字）
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
        },
        "compose": {"kp_per_baseline": True},
        "review": {},
        # v3 新增：需求明确度判定 + 反问 + 预算校验
        "clarity_check": {"rules_source": "requirement_rules"},  # 规则从 requirement_rules 表读
        "cond_clarity": {"expr": "clarity == 'unclear' and not clarity_capped"},
        "ask_user": {"templates_source": "requirement_rules"},  # 话术从 requirement_rules 表读
        "budget_check": {"underspend_threshold": 0.5},  # 方案价/预算 低于此值提示"可升级"
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

    def close(self):
        self.session.close()
