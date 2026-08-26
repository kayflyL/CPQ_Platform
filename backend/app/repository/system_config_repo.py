"""Repository for system_config table"""

import json

from pathlib import Path

from copy import deepcopy

from datetime import datetime

from typing import Optional, Any

from sqlalchemy.orm import Session

from ..models.base import Rules_SessionLocal

from ..models.system_config import SystemConfig





def _load_reasoning_prompt_defaults() -> dict:

    """读取打包的默认提示词/话术种子（不依赖 prompt_store，避免循环 import）。"""

    try:

        p = Path(__file__).resolve().parents[1] / "services" / "reasoning_prompt_defaults.json"

        return json.loads(p.read_text(encoding="utf-8"))

    except Exception:

        return {}


def _load_reasoning_node_defaults() -> dict:
    """读取打包的需求分析节点默认配置种子（不依赖业务 service，避免循环 import）。"""
    try:
        p = Path(__file__).resolve().parents[1] / "services" / "reasoning_node_defaults.json"
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}



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
    "GPU card": {"key": "gpu", "candidate_source": "catalog", "allow_absent": True, "absent_value_enum": ["none", "self_provided"], "required_by_type": {"llm_inference": True, "ai": True, "ai_accelerated": True, "domestic_compliance": False}},
    "GPU Card": {"key": "gpu", "candidate_source": "catalog", "allow_absent": True, "absent_value_enum": ["none", "self_provided"], "required_by_type": {"llm_inference": True, "ai": True, "ai_accelerated": True, "domestic_compliance": False}},
    "NIC card": {"key": "nic", "candidate_source": "catalog"},
    "NIC": {"key": "nic", "candidate_source": "catalog"},
    "Network(NIC) requirement": {"key": "nic", "candidate_source": "catalog"},
    "RAID": {"key": "raid", "candidate_source": "catalog"},
    "Raid card": {"key": "raid", "candidate_source": "catalog"},
    "Raid Card": {"key": "raid", "candidate_source": "catalog"},
    "RAID Card": {"key": "raid", "candidate_source": "catalog"},
    "Power Supply": {"key": "psu", "candidate_source": "catalog"},
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

        "tool_ids": ["query_cpq_data"],

        "data_sources": ["opportunities"],

        "permission_policy": "readonly",

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

        "tool_ids": ["query_cpq_data"],

        "data_sources": ["opportunities", "dashboard"],

        "permission_policy": "readonly",

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

        "tool_ids": ["select_models", "pick_kp_parts", "build_plan", "cost_breakdown"],

        "data_sources": ["kp_price", "bom", "cost"],

        "permission_policy": "readonly",

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

        "tool_ids": ["select_models", "pick_kp_parts", "build_plan", "search_cases",
                     "list_server_types", "list_server_models", "get_server_model"],

        "data_sources": ["requirement", "candidate_search", "bom", "server_catalog", "server_product_content"],

        "permission_policy": "readonly",

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

        "tool_ids": ["query_cpq_data", "cost_breakdown", "quote_draft"],

        "data_sources": ["quotation", "opportunity"],

        "permission_policy": "readonly",

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



    def init_defaults(self):

        """Initialize default configs if not exist"""

        defaults = [

            {"key": "tax_rate", "value": "0.13", "type": "number", "description": "税率"},

            {"key": "usd_to_rmb", "value": "7.0", "type": "number", "description": "美元兑人民币汇率"},

            {"key": "profit_margin", "value": "0.1", "type": "number", "description": "默认利润率（成本加成的默认目标利润率，非告警阈值）"},

            {"key": "default_markup_coefficient", "value": "0.10", "type": "number", "description": "默认成本加成系数（一期固定简易加成；精细化客户分层/阶梯加成二期补）"},

            {"key": "warranty_fee_rate", "value": "0.02", "type": "number", "description": "质保费率"},

            {"key": "warranty_desc_l6", "value": "质保3年，非人为及不可抗力引起的故障，软件FW问题支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "L6 默认质保条款"},

            {"key": "warranty_desc_kp", "value": "质保1年，非人为及不可抗力引起的故障，支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "KP 默认质保条款"},

            {"key": "server_series", "value": json.dumps([{"value": "Orion", "label": "Orion"}, {"value": "Polaris", "label": "Polaris"}, {"value": "Intel", "label": "Intel"}, {"value": "工作站", "label": "工作站"}], ensure_ascii=False), "type": "json", "description": "服务器系列选项（全平台唯一权威源：基准配置/机型/料件适用机型/商机平台类型）"},

            # KP 配件库筛选白名单：每品类只显业内关键 spec（不堆全部），Brand 另算（kp_parts.brand），管理面可改，拒绝硬编码

            {"key": "kp_filter_dims", "value": json.dumps({

                "HDD/SSD": ["Capacity", "Type", "Form Factor", "Media"],

                "Memory": ["Capacity", "Type", "Speed"],

                "GPU": ["Capacity", "Architecture", "tdp"],

                "CPU": ["Cores", "tdp", "Socket"],

                "Network(NIC) requirement": ["Link Speed", "Ports", "接口"],

                "Raid card": ["Ports", "Cache", "电容"]

            }, ensure_ascii=False), "type": "json", "description": "KP 筛选白名单：每品类只显这些 spec 维度（业内关键，不堆全部）；Brand 另算（kp_parts.brand 并进第一组）；管理面 system-config 可改"},

            # 需求分析：电源瓦数推断（技术员按 GPU 功耗选电源的自动化规则，可调，拒绝硬编码）

            {"key": "psu_inference", "value": json.dumps({

                "high_tdp_gpus": ["H100", "A100", "H200", "B200", "B100", "L40", "MI300",

                                  "RTX PRO", "RTX 6000", "RTX 5090"],

                "tiers": [

                    {"min_gpu": 8, "high_tdp": True, "wattage": "2700"},

                    {"min_gpu": 1, "high_tdp": False, "wattage": "2000"},

                ],

                "no_gpu_wattage": "1600",

            }, ensure_ascii=False), "type": "json", "description": "电源瓦数推断配置（high_tdp_gpus 高功耗 GPU 关键词；tiers 档位：满足 min_gpu+high_tdp 用 wattage；无 GPU 用 no_gpu_wattage）"},

            # 需求分析：CPU/GPU 型号家族词（clarity「型号双命中→明确」判定的词法分类词表，可编辑；

            # 由 startup 的 model_family_sync 从 kp 库自动补齐新型号，只加不删）

            {"key": "model_family_words", "value": json.dumps({

                "CPU": ["epyc", "xeon", "至强", "kh-", "kh50"],

                "GPU": ["h100", "a100", "h200", "h800", "a800", "b200", "b100", "l40", "l20",

                        "mi300", "mi250", "mi100", "rtx", "r9700", "w7900", "w7800", "w6600",

                        "tesla", "quadro", "radeon", "instinct", "v100", "a30", "a10"],

            }, ensure_ascii=False), "type": "json", "description": "CPU/GPU 型号家族词表（型号 token 词法归类用；startup 自动从 kp 库补齐新型号）"},

            {"key": "server_form_factor", "value": json.dumps([{"value": "2U", "label": "2U"}, {"value": "4U", "label": "4U"}, {"value": "4.5U", "label": "4.5U"}, {"value": "5U", "label": "5U"}], ensure_ascii=False), "type": "json", "description": "服务器形态选项"},

            # AI 设置

            {"key": "ai_assistant_config", "value": json.dumps({

                "chat_system_prompt": (

                    "你是 CPQ 平台的「方案助手」，辅助销售/FAE 做服务器配置与报价。"

                    "你有业务数据查询能力，可通过系统数据工具按需查询商机/配置/平台/机箱/排行/趋势/统计等数据；"

                    "用户当前所在页面的业务上下文会以「当前上下文」形式提供给你，作答时优先基于它。"

                    "要求:1) 用中文回复;2) 对料号价格、库存、具体型号编号等易变信息，不要编造——"

                    "不确定时请用户在配置页确认或查料号库;3) 回答简洁、分点。"

                ),

                "response_style": "detailed",

                "data_query_triggers": (

                    "商机,配置,平台,机箱,排行,排名,趋势,走势,重点,统计,新增,分布,环比,"

                    "query_cpq_data,利润,上周,本周,这周,本月,这个月,上月,上个月,"

                    "近半年,半年,近一年,今年,去年,季度"

                ),

                # 上下文 Provider 配置（拒绝硬编码；启用 + 显示名，不再存简要/详细）

                "providers": {

                    "quote": {"enabled": True, "label": "报价工作台"},

                    "opportunity": {"enabled": True, "label": "商机详情"},

                    "opportunity-list": {"enabled": True, "label": "商机线索"}

                }

            }, ensure_ascii=False), "type": "json", "description": "AI 方案助手设置"},

            {"key": "requirement_slots", "value": json.dumps({"version": 1, "ask_threshold": 2, "slots": _DEFAULT_REQUIREMENT_SLOTS}, ensure_ascii=False), "type": "json", "description": "需求期望槽位清单/线索登记表字段（唯一权威源：理解/反问/前端进度卡/编辑器统一按此配置；部件动态来自 KP，不在此清单内）"},
            {"key": "kp_slot_group_map", "value": json.dumps(_DEFAULT_KP_SLOT_GROUP_MAP, ensure_ascii=False), "type": "json", "description": "KP 大类 → 归一部件槽位映射（动态生成「部件」进度卡/反问题目；未映射的大类作为自由行不进强制统计）"},

            # LLM API 配置（支持前端可视化修改，优先级高于 .env）

            {"key": "llm_config", "value": json.dumps({

                "enabled": True,  # 统一 AI 引擎开关（设置-AI 设置-启用 AI）；关闭后所有 AI 能力走规则/不调 LLM

                "base_url": "",  # 留空则用 .env 的 LLM_BASE_URL

                "api_key": "",   # 留空则用 .env 的 LLM_API_KEY

                "model": "",     # 留空则用 .env 的 LLM_MODEL

                "temperature": 0.7,

                "max_tokens": 8000,

            }, ensure_ascii=False), "type": "json", "description": "LLM API 配置（base_url/api_key/model 留空则用 .env 环境变量）"},

             # AI 同事配置：角色化 AI 能力（总助/专业同事）。

             # 注意：角色列表、工具、入口均来自 system_config，业务代码不做角色硬编码。

             {"key": "ai_colleagues", "value": json.dumps({

                 "version": 1,

                 "team_meta": {

                     "name": "CPQ AI 团队",

                     "description": "负责商机、选型、成本与报价的 AI 团队",

                     "color": "#1677ff",

                 },

                 "dispatch_enabled": True,

                 "dispatch_rules": _DEFAULT_AI_COLLEAGUE_DISPATCH_RULES,

                 "colleagues": _DEFAULT_AI_COLLEAGUES,

                 "access_policy": {

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

                 },

                 "layout": {"nodes": [], "edges": []},

             }, ensure_ascii=False), "type": "json", "description": "AI 同事配置（角色/人设/工具/入口/权限/团队/布局，业务代码从 system_config 读取）"},

            {"key": "reasoning_prompts", "value": json.dumps(_load_reasoning_prompt_defaults(), ensure_ascii=False), "type": "json", "description": "需求分析节点提示词/话术默认值（用户可在节点抽屉覆盖）"},

            {"key": "reasoning_node_defaults", "value": json.dumps(_load_reasoning_node_defaults(), ensure_ascii=False), "type": "json", "description": "需求分析节点非提示词默认配置（白盒回显与保存去重时唯一权威源）"},


            {"key": "bom_category_aliases", "value": json.dumps({
                "heatsink": ["散热器", "散热"],
                "fan": ["风扇"],
                "rail": ["滑轨", "导轨", "rail", "slide"],
                "chassis": ["机箱"],
                "backplane": ["背板"],
                "cable": ["线缆", "cable"],
                "psu": ["电源", "psu", "power supply"],
            }, ensure_ascii=False), "type": "json", "description": "BOM 模板品类中英别名：模板 row 常填英文 category（heatsink/fan/rail/chassis/backplane/cable/psu），底盘件 parts_master category 多为中文，用此别名跨语言匹配零件；仅作为零件匹配用词表，可编辑。"},
        ]

        

        for d in defaults:

            existing = self.session.query(SystemConfig).filter(SystemConfig.key == d["key"]).first()

            if not existing:

                config = SystemConfig(

                    key=d["key"],

                    value=d["value"],

                    type=d["type"],

                    description=d["description"],

                    updated_at=datetime.now().isoformat(),

                    updated_by="system"

                )

                self.session.add(config)

        

        # 已废弃：scene_analysis 节点下线，清理 scene_mapping 脏数据（幂等）

        self.session.query(SystemConfig).filter(SystemConfig.key == "scene_mapping").delete()

        self.session.commit()

        self._ensure_ai_colleagues_dispatch_defaults()

        self._ensure_requirement_slots()
        self._ensure_kp_slot_group_map()
        self._ensure_semantic_contract()



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

                        cur_tools = colleague.get("tool_ids") or []

                        if colleague.get("tool_ids") == ["select_models", "query_cpq_data"] or not all(
                                t in cur_tools for t in ("list_server_types", "list_server_models", "get_server_model")):

                            colleague["tool_ids"] = deepcopy(default_colleague["tool_ids"])

                            changed = True

                        cur_sources = colleague.get("data_sources") or []

                        if not all(s in cur_sources for s in ("server_catalog", "server_product_content")):

                            colleague["data_sources"] = deepcopy(default_colleague["data_sources"])

                            changed = True

                    if role_key == "cost_analyst" and colleague.get("tool_ids") == ["select_models", "pick_kp_parts", "build_plan"]:

                        colleague["tool_ids"] = deepcopy(default_colleague["tool_ids"])

                        changed = True

                    if role_key == "quote_specialist" and colleague.get("tool_ids") == ["query_cpq_data"]:

                        colleague["tool_ids"] = deepcopy(default_colleague["tool_ids"])

                        changed = True

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
