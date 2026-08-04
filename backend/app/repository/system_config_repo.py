"""Repository for system_config table"""
import json
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.system_config import SystemConfig


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
        from app.services.scene_analyzer import DEFAULT_SCENE_MAPPING
        defaults = [
            {"key": "tax_rate", "value": "0.13", "type": "number", "description": "税率"},
            {"key": "usd_to_rmb", "value": "7.0", "type": "number", "description": "美元兑人民币汇率"},
            {"key": "profit_margin", "value": "0.1", "type": "number", "description": "默认利润率（成本加成的默认目标利润率，非告警阈值）"},
            {"key": "profit_margin_alert_threshold", "value": "0.08", "type": "number", "description": "利润率告警阈值：报价利润率低于此值时弹窗提示走线下特价审批"},
            {"key": "default_markup_coefficient", "value": "0.10", "type": "number", "description": "默认成本加成系数（一期固定简易加成；精细化客户分层/阶梯加成二期补）"},
            {"key": "warranty_fee_rate", "value": "0.02", "type": "number", "description": "质保费率"},
            {"key": "warranty_desc_l6", "value": "质保3年，非人为及不可抗力引起的故障，软件FW问题支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "L6 默认质保条款"},
            {"key": "warranty_desc_kp", "value": "质保1年，非人为及不可抗力引起的故障，支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "KP 默认质保条款"},
            {"key": "server_series", "value": json.dumps([{"value": "Orion", "label": "Orion"}, {"value": "Polaris", "label": "Polaris"}, {"value": "Intel", "label": "Intel"}, {"value": "工作站", "label": "工作站"}], ensure_ascii=False), "type": "json", "description": "服务器系列选项（全平台唯一权威源：基准配置/机型/料件适用机型/商机平台类型）"},
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
            # 需求分析：目录引导的客户话术识别词（默认回答/委托/规格提示正则），可编辑
            # 需求分析：CPU/GPU 型号家族词（clarity「型号双命中→明确」判定的词法分类词表，可编辑；
            # 由 startup 的 model_family_sync 从 kp 库自动补齐新型号，只加不删）
            {"key": "model_family_words", "value": json.dumps({
                "CPU": ["epyc", "xeon", "至强", "kh-", "kh50"],
                "GPU": ["h100", "a100", "h200", "h800", "a800", "b200", "b100", "l40", "l20",
                        "mi300", "mi250", "mi100", "rtx", "r9700", "w7900", "w7800", "w6600",
                        "tesla", "quadro", "radeon", "instinct", "v100", "a30", "a10"],
            }, ensure_ascii=False), "type": "json", "description": "CPU/GPU 型号家族词表（型号 token 词法归类用；startup 自动从 kp 库补齐新型号）"},
            {"key": "requirement_guide_words", "value": json.dumps({
                "default": ["不确定", "你推荐", "还没定", "越大越好", "都可以", "不限", "随便", "您推荐", "帮我选"],
                "delegate": ["你帮我推荐", "帮我推荐", "你来推荐", "你推荐", "你定", "你来定", "你看着办",
                             "听你的", "随便", "都行", "都可以", "怎么都行", "帮我选", "你帮选", "帮我来一台"],
                "spec_hint_re": ["cpu", "内存", "gpu", "硬盘", "ssd", "hdd", "nvme", "raid", "网卡",
                                 "万兆", "千兆", "机架", "塔式", "[1-8]\\s*u\\b", "核", "颗", "条", "张"],
            }, ensure_ascii=False), "type": "json", "description": "需求分析引导话术识别：default=「不确定/你推荐」等放弃指定；delegate=委托推荐；spec_hint_re=贴了规格清单的提示（正则列表，小写）"},
            {"key": "server_form_factor", "value": json.dumps([{"value": "2U", "label": "2U"}, {"value": "4U", "label": "4U"}, {"value": "4.5U", "label": "4.5U"}, {"value": "5U", "label": "5U"}], ensure_ascii=False), "type": "json", "description": "服务器形态选项"},
            # AI 设置
            {"key": "ai_assistant_config", "value": json.dumps({
                "auto_context": True,
                "context_detail": "brief",
                "response_style": "detailed",
                # 上下文 Provider 配置（拒绝硬编码）
                "providers": {
                    "quote": {"enabled": True, "label": "报价工作台", "detail": "brief"},
                    "opportunity": {"enabled": True, "label": "商机详情", "detail": "brief"},
                    "opportunity-list": {"enabled": True, "label": "商机线索", "detail": "brief"}
                }
            }, ensure_ascii=False), "type": "json", "description": "AI 方案助手设置"},
            {"key": "ai_trend_analysis", "value": json.dumps({
                "highlight_count": 10,
                # 趋势分析提示词模板（方案助手「分析本期趋势」快捷指令用，前端可改，反对硬编码）
                "prompt_template": (
                    "你是 CPQ 平台的数据分析师。下面提供「本周/本月/近半年」三个周期的商机聚合数据,以及近期重点商机明细。"
                    "请输出一份结构化趋势洞察报告,严格按以下分节:\n\n"
                    "# 一、周数据\n本周商机数、各平台商机数与配置数。\n\n"
                    "# 二、月数据\n本月商机数、各平台商机数与配置数。\n\n"
                    "# 三、半年度商机趋势\n近半年逐月商机数与环比变化(自行计算),点出趋势方向(连续增长/回落/新高)。\n\n"
                    "# 四、平台格局\n近半年各平台商机数与占比;若主导平台发生切换,描述切换方向。切换原因可推测,但必须标注「(推测)」。\n\n"
                    "# 五、机箱形态\n近半年各机箱形态占比。\n\n"
                    "# 六、半年业务 TOP5\n近半年销售人员商机数前五。\n\n"
                    "# 七、近期重点商机\n列出提供的近期重点商机(客户/平台/机箱/台数/状态)。\n\n"
                    "# 八、关键洞察\n用 ✅⚠️🔥📊 标注 3-5 条:增长信号、风险信号、结构变化、值得跟进的重点。归因性结论标注「(推测/待核实)」。\n\n"
                    "要求:只使用提供的数据;占比与环比自行计算;未提供的信息(如具体成交价)不要编造。"
                )
            }, ensure_ascii=False), "type": "json", "description": "AI 趋势分析设置（方案助手快捷指令的提示词模板与重点商机条数）"},
            # 场景分析映射（scene_analysis 节点）：AI/存储/通用场景规则 + 系列/形态推断 + 商机上下文偏好。
            # 权威数据源（策略中心可编辑）；种子取 scene_analyzer.DEFAULT_SCENE_MAPPING，改映射先改常量再重种。
            {"key": "scene_mapping", "value": json.dumps(DEFAULT_SCENE_MAPPING, ensure_ascii=False),
             "type": "json", "description": "场景分析映射：场景规则/系列形态推断/商机上下文偏好（scene_analysis 节点数据源）"},
            # 需求期望槽位清单（clarity_check 明确度判定数据源）：L0 底线/L1 重要/L2 系统推导。
            {"key": "requirement_slots", "value": json.dumps({
                "version": 1,
                "ask_threshold": 2,
                "slots": [
                    {"key": "scene", "label": "应用场景", "level": "L0"},
                    {"key": "series", "label": "所属系列", "level": "L0"},
                    {"key": "cpu", "label": "CPU", "level": "L0"},
                    {"key": "memory", "label": "内存", "level": "L0"},
                    {"key": "storage", "label": "存储", "level": "L0", "default_ok": True},
                    {"key": "form", "label": "机箱形态", "level": "L1"},
                    {"key": "gpu", "label": "GPU", "level": "L1"},
                    {"key": "nic", "label": "网卡", "level": "L1"},
                    {"key": "raid", "label": "阵列卡", "level": "L2"},
                    {"key": "psu", "label": "电源", "level": "L2"},
                ],
            }, ensure_ascii=False), "type": "json", "description": "需求期望槽位清单（clarity 明确度：L0 底线缺≥2 反问 / L1 重要提示可补 / L2 系统推导）"},
            # LLM API 配置（支持前端可视化修改，优先级高于 .env）
            {"key": "llm_config", "value": json.dumps({
                "enabled": True,  # 统一 AI 引擎开关（设置-AI 设置-启用 AI）；关闭后所有 AI 能力走规则/不调 LLM
                "base_url": "",  # 留空则用 .env 的 LLM_BASE_URL
                "api_key": "",   # 留空则用 .env 的 LLM_API_KEY
                "model": "",     # 留空则用 .env 的 LLM_MODEL
                "system_prompt": "你是 CPQ 平台的「方案助手」,辅助销售/FAE 做服务器配置与报价。用户当前所在页面的业务上下文会以「当前上下文」形式提供给你,作答时优先基于它。要求:1) 用中文回复;2) 对料号价格、库存、具体型号编号等易变信息,不要编造——不确定时请用户在配置页确认或查料号库;3) 回答简洁、分点。",
                "temperature": 0.7,
                "max_tokens": 8000,
            }, ensure_ascii=False), "type": "json", "description": "LLM API 配置（base_url/api_key/model 留空则用 .env 环境变量）"},
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
        
        self.session.commit()

    def close(self):
        self.session.close()
