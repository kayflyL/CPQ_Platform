"""Repository for system_config table"""

import json

from pathlib import Path

from copy import deepcopy

from datetime import datetime

from typing import Optional, Any

from sqlalchemy.orm import Session

from ..models.base import Rules_SessionLocal

from ..models.system_config import SystemConfig





_DEFAULT_REQUIREMENT_SLOTS: list = [
    {"key": "server_type", "label": "服务器类型", "level": "L0", "group": "基本信息", "candidate_source": "catalog"},
    {"key": "server_model", "label": "机型", "level": "L2", "group": "基本信息", "candidate_source": "catalog"},
    {"key": "platform_type", "label": "平台/系列", "level": "L0", "group": "基本信息", "candidate_source": "catalog"},
    {"key": "chassis_form", "label": "机箱形态", "level": "L1", "group": "基本信息", "candidate_source": "catalog"},
    {"key": "purchase_qty", "label": "数量", "level": "L0", "group": "基本信息", "candidate_source": "free"},
    {"key": "warranty_years", "label": "保修年限", "level": "L2", "group": "基本信息", "candidate_source": "free"},
]





_DEFAULT_KP_SLOT_GROUP_MAP: dict = {
    "CPU": {"key": "cpu", "candidate_source": "catalog"},
    "Memory": {"key": "memory", "candidate_source": "catalog"},
    "HDD/SSD": {"key": "storage", "candidate_source": "catalog"},
    "GPU": {"key": "gpu", "candidate_source": "catalog", "allow_absent": True, "absent_value_enum": ["none", "self_provided"], "required_by_type": {"llm_inference": True, "ai": True, "ai_accelerated": True, "domestic_compliance": False}},
    "NIC": {"key": "nic", "candidate_source": "catalog"},
    "Raid card": {"key": "raid", "candidate_source": "catalog"},
}


_DEFAULT_SEMANTIC_CONTRACT: dict = {
    "version": 1,
    "container_key": "semantic",
    "dimensions": [
        {"key": "intent", "label": "使用意图", "kind": "single_enum",
         "values": ["general", "compute", "virtualization", "database", "llm_inference", "storage", "domestic_compliance"],
         "ask_policy": "auto"},
        {"key": "exclusions", "label": "明确排除/自购", "kind": "map",
         "value_keys": ["cpu", "memory", "gpu", "nic", "raid", "psu"],
         "value_enum": ["none", "self_provided"]},
        {"key": "compliance", "label": "合规要求", "kind": "group",
         "fields": [{"key": "domestic_only", "label": "国产化", "type": "bool", "default": False}]},
        {"key": "workload", "label": "工作负载", "kind": "struct",
         "fields": [{"key": "kind", "enum": ["llm_inference", "virtualization", "database", "general"]},
                    {"key": "model", "type": "string"},
                    {"key": "total_vram_gb", "type": "number"},
                    {"key": "gpu_count", "type": "number"}]}
    ]
}


# AI 同事自动分派规则（配置默认值；业务代码不读这份常量，只作为 seed/迁移兜底）。

_DEFAULT_AI_COLLEAGUE_DISPATCH_RULES = [

    {

        "role_key": "support_engineer",

        "enabled": True,

        "keywords": [

            "需求分析", "需求", "选型", "bom", "配置", "服务器", "机箱",

            "ai服务器", "存储服务器", "通用服务器", "gpu", "配一台", "买服务器",

        ],

        "entry_points": ["AiOffice"],

    },

    {

        "role_key": "cost_analyst",

        "enabled": True,

        "keywords": [

            "成本", "成本测算", "成本明细", "成本结构", "整机成本", "bom 成本",

        ],

        "entry_points": ["StrategySelection"],

    },

    {

        "role_key": "data_analyst",

        "enabled": True,

        "keywords": [

            "趋势", "统计", "排行", "平台分布", "机箱分布", "利润率",

            "商机数", "配置数", "重点商机",

        ],

        "entry_points": ["Opportunities"],

    },

    {

        "role_key": "quote_specialist",

        "enabled": True,

        "keywords": [

            "报价", "报价单", "报价构成", "报价说明", "价格", "折扣",

        ],

        "entry_points": ["Workspace", "OpportunityDetail"],

    },

]



_ENTRY_POINT_MIGRATIONS = {

    "requirement_analysis": "AiOffice",

    "StrategyRequirement": "AiOffice",

    "selection_config": "StrategySelection",

}

# 2026-08-29 步骤2 退役：query_cpq_data（坏）→ query_data（映射）；服务器浏览三件套直接剔除
# 工具名唯一真源迁移到 services/tool_names.py，此处只引用共享版，避免散落双写。
from ..services.tool_names import TOOL_RENAME_MAP as _TOOL_RENAME_MAP, RETIRED_TOOL_IDS as _RETIRED_TOOL_IDS





_DEFAULT_AI_COLLEAGUES = [

    {

        "role_key": "assistant",

        "name": "总助 / 方案助手",

        "color": "#1677ff",

        "avatar_url": "",

        "enabled": True,

        "system_prompt": (

            "你是 CPQ 平台的总助，负责理解用户意图、回答业务问题，并在需要专业能力时分派给合适的 AI 同事。"

            "你可以查询业务数据，但不直接写核心业务数据；涉及易变信息必须基于系统数据回答。"

        ),

        "opening_message": "我是 CPQ 平台的总助，可以帮你查询业务数据、分析趋势，并转接需求分析、成本核算或报价同事。",

        "response_style": "detailed",

        "model_override": None,

        "tool_ids": ["query_data"],

        "data_boundary": {
            "mode": "allow_read",
            "schemas": [],
            "tables_allow": [
                "opportunities.opportunities",
                "opportunities.opportunity_requirements",
                "opportunities.opportunity_bom_schemes",
                "opportunities.quotations",
                "opportunities.quotation_items",
                "l6.server_types",
                "l6.server_models",
                "l6.base_configs",
            ],
            "masked_fields": [],
        },

        "data_sources": ["opportunities"],


        "dispatchable": False,

    },

    {

        "role_key": "data_analyst",

        "name": "数据分析师",

        "color": "#52c9a0",

        "avatar_url": "",

        "enabled": True,

        "system_prompt": (

            "你是 CPQ 平台的数据分析师，负责商机、配置、平台、机箱、排行、趋势和利润率等统计洞察。"

            "只做数据读取与分析，不修改业务数据，输出结论要基于系统数据并标注不确定性。"

        ),

        "opening_message": "我可以分析商机趋势、平台与机箱分布、销售排行和机型利润率，需要我查哪块数据？",

        "response_style": "detailed",

        "model_override": None,

        "tool_ids": [],

        "data_sources": ["opportunities", "dashboard"],


        "dispatchable": True,

    },

    {

        "role_key": "cost_analyst",

        "name": "成本核算",

        "color": "#fa8c16",

        "avatar_url": "",

        "enabled": True,

        "system_prompt": (

            "你是 CPQ 平台的成本核算同事，负责机箱、配件和整机成本测算、差异分析。"

            "价格、成本等易变信息必须基于系统规则和数据，不得编造；分析结果以草稿形式输出。"

        ),

        "opening_message": "我可以帮你测算整机 BOM 成本、分析成本结构，请告诉我当前机型或配置。",

        "response_style": "detailed",

        "model_override": None,

        "tool_ids": ["choose_model"],

        "data_sources": ["kp_price", "bom", "cost"],


        "dispatchable": True,

    },

    {

        "role_key": "support_engineer",

        "name": "技术支持工程师",

        "color": "#1677ff",

        "avatar_url": "",

        "enabled": True,

        "system_prompt": (

            "你是 CPQ 平台的技术支持工程师，负责把客户需求转化为服务器配置方案。"

            "语气轻松亲切，像懂行又友好的同事；用户闲聊/问身份/题外话时用一两句友好回应，再温和带回正题，不生硬拒绝。"

            "只做理解与编排：型号、料号、价格、兼容性、BOM 一律来自工具或规则库，绝不编造；涉及这类易变信息时说'选型后我帮你确认'。"

            "默认中文，回复自然、短而有信息量，不机械复读、不堆黑话。"

        ),

        "opening_message": "嗨，我是 CPQ 的技术支持工程师 😊 告诉我你的业务场景（跑数据库、虚拟化、还是 AI 训练？），我来帮你搭最合适的服务器整机方案～也可以直接描述需求。",

        "response_style": "detailed",

        "model_override": None,

        "tool_ids": ["choose_model", "search_cases"],

        "data_sources": ["requirement", "candidate_search", "bom", "server_catalog", "server_product_content"],


        "dispatchable": True,

    },

    {

        "role_key": "quote_specialist",

        "name": "市场报价专员",

        "color": "#a855f7",

        "avatar_url": "",

        "enabled": True,

        "system_prompt": (

            "你是 CPQ 平台的市场报价专员，负责生成报价单草稿并解释价格构成。"

            "正式报价单导出前必须经过用户确认；价格、折扣、客户和商机信息必须基于系统数据。"

        ),

        "opening_message": "我可以帮你生成报价单草稿、解释价格构成，请把商机或配置发给我。",

        "response_style": "detailed",

        "model_override": None,

        "tool_ids": [],

        "data_sources": ["quotation", "opportunity"],


        "dispatchable": True,

    },

]





class SystemConfigRepository:

    def __init__(self):

        self.session: Session = Rules_SessionLocal()



    def get(self, key: str) -> Optional[dict]:

        """Get config by key"""

        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()

        return config.to_dict() if config else None



    def get_value(self, key: str, default: Any = None) -> Any:

        """Get config value with type conversion"""

        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()

        if not config:

            return default

        

        value = config.value

        config_type = config.type or 'string'

        

        if config_type == 'number':

            try:

                return float(value) if '.' in value else int(value)

            except (ValueError, TypeError):

                return default

        elif config_type == 'boolean':

            return value.lower() in ('true', '1', 'yes')

        elif config_type == 'json':

            try:

                return json.loads(value)

            except json.JSONDecodeError:

                return default

        return value



    def get_all(self) -> list[dict]:

        """Get all configs"""

        configs = self.session.query(SystemConfig).order_by(SystemConfig.key).all()

        return [c.to_dict() for c in configs]



    def set(self, key: str, value: Any, type: str = 'string', description: str = None, operator: str = 'system') -> dict:

        """Set config value (create or update)"""

        now = datetime.now().isoformat()

        

        # Convert value to string

        if isinstance(value, (dict, list)):

            str_value = json.dumps(value, ensure_ascii=False)

            type = 'json'

        elif isinstance(value, bool):

            str_value = str(value).lower()

            type = 'boolean'

        elif isinstance(value, (int, float)):

            str_value = str(value)

            type = 'number'

        else:

            str_value = str(value)

            type = type or 'string'

        

        existing = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()

        if existing:

            existing.value = str_value

            existing.type = type

            if description is not None:

                existing.description = description

            existing.updated_at = now

            existing.updated_by = operator

            self.session.commit()

            return existing.to_dict()

        else:

            config = SystemConfig(

                key=key,

                value=str_value,

                type=type,

                description=description,

                updated_at=now,

                updated_by=operator

            )

            self.session.add(config)

            self.session.commit()

            return config.to_dict()



    def delete(self, key: str) -> bool:

        """Delete config by key"""

        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()

        if not config:

            return False

        self.session.delete(config)

        self.session.commit()

        return True




    def _ensure_ai_colleagues_dispatch_defaults(self):

        """把 AI 同事分派规则作为配置默认补进旧库，并迁移旧入口标识；只补缺失字段、不覆盖用户编辑。"""

        cfg = self.get_value("ai_colleagues")

        if isinstance(cfg, list):

            cfg = {"version": 1, "colleagues": cfg}

        if not isinstance(cfg, dict):

            return

        changed = False

        if not isinstance(cfg.get("access_policy"), dict):

            cfg["access_policy"] = {

                "enabled": True,

                "default_room_ids": ["default"],

                "role_room_map": {"member": ["default"]},

                "user_room_map": {},

                "default_chat_role_keys": ["assistant"],

                "role_chat_role_keys": {

                    "business": ["assistant"],

                    "te": ["support_engineer"],

                    "cost": ["cost_analyst"],

                    "quote": ["quote_specialist"],

                    "member": ["assistant"],

                },

                "user_chat_role_keys": {},

            }

            changed = True

        else:

            policy = cfg["access_policy"]

            if "default_chat_role_keys" not in policy:

                policy["default_chat_role_keys"] = ["assistant"]

                changed = True

            if "role_chat_role_keys" not in policy:

                policy["role_chat_role_keys"] = {

                    "business": ["assistant"],

                    "te": ["support_engineer"],

                    "cost": ["cost_analyst"],

                    "quote": ["quote_specialist"],

                    "member": ["assistant"],

                }

                changed = True

            if "user_chat_role_keys" not in policy:

                policy["user_chat_role_keys"] = {}

                changed = True

        if not isinstance(cfg.get("team_meta"), dict):

            cfg["team_meta"] = {

                "name": "CPQ AI 团队",

                "description": "负责商机、选型、成本与报价的 AI 团队",

                "color": "#1677ff",

            }

            changed = True

        if not isinstance(cfg.get("layout"), dict):

            cfg["layout"] = {"nodes": [], "edges": []}

            changed = True

        default_map = {c["role_key"]: c for c in _DEFAULT_AI_COLLEAGUES}

        colleagues = cfg.get("colleagues")

        if not isinstance(colleagues, list):

            colleagues = []

            changed = True

        else:

            for colleague in colleagues:

                if not isinstance(colleague, dict):

                    continue

                if "icon" in colleague:

                    colleague.pop("icon", None)

                    changed = True

                if "entry_points" in colleague:

                    colleague.pop("entry_points", None)

                    changed = True

                role_key = colleague.get("role_key")

                default_colleague = default_map.get(role_key)

                if default_colleague:

                    for key, default_value in default_colleague.items():

                        if key not in colleague or colleague.get(key) is None:

                            colleague[key] = deepcopy(default_value)

                            changed = True

                    if role_key == "support_engineer":

                        cur_sources = colleague.get("data_sources") or []

                        if not all(s in cur_sources for s in ("server_catalog", "server_product_content")):

                            colleague["data_sources"] = deepcopy(default_colleague["data_sources"])

                            changed = True

                    if role_key == "cost_analyst" and colleague.get("tool_ids") == ["choose_model", "build_plan", "cost_breakdown"]:

                        colleague["tool_ids"] = deepcopy(default_colleague["tool_ids"])

                        changed = True

                # 2026-08-29 步骤2：query_data 原语上线，退役 query_cpq_data 与服务器浏览三件套。
                # 名字映射 + 剔除退役项；方案助手（试点）同时补白名单表进数据边界。

                if isinstance(colleague.get("tool_ids"), list):

                    mapped = []

                    touched = False

                    for t in colleague["tool_ids"]:

                        t = str(t or "").strip()

                        if not t:
                            continue

                        next_t = _TOOL_RENAME_MAP.get(t, t)
                        # 试点只开方案助手：query_cpq_data→query_data 映射仅限 assistant，其余角色直接剔除
                        if t == "query_cpq_data" and role_key == "assistant":
                            next_t = "query_data"

                        if next_t != t or t in _RETIRED_TOOL_IDS:

                            touched = True

                        if next_t not in _RETIRED_TOOL_IDS and next_t not in mapped:

                            mapped.append(next_t)

                    if touched:

                        colleague["tool_ids"] = mapped

                        changed = True

                        if role_key == "assistant":

                            boundary = colleague.get("data_boundary")

                            if isinstance(boundary, dict) and boundary.get("mode") == "allow_read":

                                allow = [str(x) for x in (boundary.get("tables_allow") or [])]

                                for table in (default_map.get("assistant") or {}).get("data_boundary", {}).get("tables_allow", []):

                                    if table not in allow:

                                        allow.append(table)

                                boundary["tables_allow"] = allow

        existing_keys = {c.get("role_key") for c in colleagues if isinstance(c, dict)}

        for default_colleague in _DEFAULT_AI_COLLEAGUES:

            if default_colleague.get("role_key") not in existing_keys:

                colleagues.append(deepcopy(default_colleague))

                changed = True

        cfg["colleagues"] = colleagues

        dispatch_rules = cfg.get("dispatch_rules")

        if not isinstance(dispatch_rules, list):

            dispatch_rules = []

            changed = True

        else:

            for rule in dispatch_rules:

                if isinstance(rule, dict) and isinstance(rule.get("entry_points"), list):

                    migrated = []

                    entry_changed = False

                    for entry_point in rule["entry_points"]:

                        next_entry = _ENTRY_POINT_MIGRATIONS.get(entry_point, entry_point)

                        if next_entry not in migrated:

                            migrated.append(next_entry)

                        if next_entry != entry_point:

                            entry_changed = True

                    if entry_changed:

                        rule["entry_points"] = migrated

                        changed = True

        rule_keys = {r.get("role_key") for r in dispatch_rules if isinstance(r, dict)}

        for default_rule in _DEFAULT_AI_COLLEAGUE_DISPATCH_RULES:

            if default_rule.get("role_key") not in rule_keys:

                dispatch_rules.append(deepcopy(default_rule))

                changed = True

        cfg["dispatch_rules"] = dispatch_rules

        if "dispatch_enabled" not in cfg:

            cfg["dispatch_enabled"] = True

            changed = True

        if changed:

            self.set("ai_colleagues", cfg, "json",

                     "AI 同事配置（角色/人设/工具/入口/权限，业务代码从 system_config 读取）",

                     "system")



    def _ensure_requirement_slots(self):
        """幂等：把 DB 的 requirement_slots 收敛为「基本信息 6 项」（部件不再落库，动态来自 KP）。

        部件 slot（cpu/memory/storage/gpu/nic/raid/psu 等）一律剔除；基本信息保留用户编辑
        （label/level/candidate_source），缺失补齐。不覆盖用户编辑。
        """
        cfg = self.get_value("requirement_slots")
        if not isinstance(cfg, dict):
            return
        alias = {"scene": "server_type", "series": "platform_type", "form": "chassis_form"}
        old_slots = cfg.get("slots")
        if not isinstance(old_slots, list):
            return
        part_keys = {"cpu", "memory", "storage", "gpu", "nic", "raid", "psu"}
        canon = {s["key"]: dict(s) for s in _DEFAULT_REQUIREMENT_SLOTS}

        def canon_of(s):
            k = str(s.get("key") or s.get("name") or "").strip()
            return alias.get(k, k)

        new_slots = []
        seen = set()
        for s in old_slots:
            if not isinstance(s, dict):
                continue
            k = canon_of(s)
            grp = str(s.get("group") or "")
            # 只剔除「部件」槽位（旧版写死的 cpu/memory/... 或 group=部件），其余（基本信息+自定义字段）保留
            if k in part_keys or grp == "部件":
                continue
            base = canon.get(k)
            if not base:
                merged = dict(s)
                merged["key"] = k
                merged.setdefault("group", grp or "其他")
                new_slots.append(merged)
                if k:
                    seen.add(k)
                continue
            merged = dict(base)
            for attr in ("label", "level", "candidate_source"):
                v = s.get(attr)
                if v not in (None, ""):
                    merged[attr] = v
            if k == "server_model":
                merged.update({"level": "L2"})
            new_slots.append(merged)
            seen.add(k)
        for base in _DEFAULT_REQUIREMENT_SLOTS:
            if base["key"] not in seen:
                new_slots.append(dict(base))
        new_cfg = {"version": 1, "ask_threshold": cfg.get("ask_threshold", 2), "slots": new_slots}
        if new_cfg != cfg:
            self.set("requirement_slots", new_cfg, "json", "需求期望槽位清单/线索登记表字段（唯一权威源：理解/反问/前端进度卡/编辑器统一按此配置；部件动态来自 KP，不在此清单内）", "system")

    def _ensure_kp_slot_group_map(self):
        """幂等：把 DB 的 kp_slot_group_map 升级为规范映射（KP 大类 → 归一部件槽位）。

        部件字段由 AI 填写，不再保留 level/required/ask/default_ok；只要存在即剔除并落库。
        """
        cfg = self.get_value("kp_slot_group_map")
        if not isinstance(cfg, dict) or not cfg:
            self.set("kp_slot_group_map", dict(_DEFAULT_KP_SLOT_GROUP_MAP), "json",
                     "KP 大类 → 归一部件槽位映射（动态生成「部件」进度卡/反问题目；未映射的大类作为自由行不进强制统计）", "system")
            return
        changed = False
        for v in cfg.values():
            if not isinstance(v, dict):
                continue
            for _k in ("level", "required", "ask", "default_ok", "label"):
                if _k in v:
                    v.pop(_k, None)
                    changed = True
        if changed:
            self.set("kp_slot_group_map", cfg, "json",
                     "KP 大类 → 归一部件槽位映射（动态生成「部件」进度卡/反问题目；未映射的大类作为自由行不进强制统计）", "system")

    def _ensure_semantic_contract(self):
        """幂等：确保存在语义契约配置（无则写默认；已存在不覆盖，保留用户编辑）。"""
        cfg = self.get_value("semantic_contract")
        if isinstance(cfg, dict) and cfg:
            return
        self.set("semantic_contract", dict(_DEFAULT_SEMANTIC_CONTRACT), "json",
                 "需求语义契约：intent/exclusions/compliance/workload 维度定义（可配），驱动智能填表与下游契约优先选配", "system")
    def reset_kp_slot_group_map(self):
        """重置 kp_slot_group_map 为规范映射。"""
        return self.set("kp_slot_group_map", dict(_DEFAULT_KP_SLOT_GROUP_MAP), "json",
                        "KP 大类 → 归一部件槽位映射（动态生成「部件」进度卡/反问题目；未映射的大类作为自由行不进强制统计）", "system")


    def reset_requirement_slots(self):

        """重置 requirement_slots 为规范种子（基本信息 6 项），供编辑器「恢复默认」使用。"""

        cfg = {"version": 1, "ask_threshold": 2, "slots": [dict(s) for s in _DEFAULT_REQUIREMENT_SLOTS]}

        return self.set("requirement_slots", cfg, "json", "需求期望槽位清单/线索登记表字段（唯一权威源：理解/反问/前端进度卡/编辑器统一按此配置；L0 底线缺≥2 反问 / L1 重要提示可补 / L2 系统推导）", "system")
    def close(self):

        self.session.close()
