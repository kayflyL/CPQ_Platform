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
            # LLM API 配置（支持前端可视化修改，优先级高于 .env）
            {"key": "llm_config", "value": json.dumps({
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
