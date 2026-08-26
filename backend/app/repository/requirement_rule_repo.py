"""Repository for rules.requirement_rules + rules.requirement_samples.

规则类型：clarity（明确度判定）/ budget（预算映射）。
旧 rebuttal/workload（臆造选项反问）已随目录驱动引导上线删除（cleanup_obsolete_rules）。
"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.requirement_rule import RequirementRule, RequirementSample


# ===== 默认规则 seed（三层兜底的最底层常量也复用这套结构） =====
_VALID_TYPE = {
    "clarity", "budget", "cpu_mem_generation", "category_alias",
    "type_package", "spec_rule", "capacity_match", "fallback_order", "check_rule",
    "platform_series_map", "cpu_vendor_map", "raid_level_map", "workload_map", "compliance_map",
    "type_alias", "model_action_phrases", "kp_action_phrases",
    "gpu_brand_map", "spec_unit_patterns", "power_calibration",
}

DEFAULT_RULES: list[dict] = [
    # ── clarity：需求明确度判定 ──
    {
        "type": "clarity", "name": "CPU+GPU 型号双命中 → 明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "model_token_in_category", "category": "CPU", "min": 1},
                {"type": "model_token_in_category", "category": "GPU", "min": 1},
            ]},
            "level": "explicit", "missing_if_not": [], "weight": 100,
            "explain": "CPU 和 GPU 型号 token 同时命中 → 需求明确",
        },
    },
    {
        "type": "clarity", "name": "系列+形态+品类≥3+预算 → 明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "series_and_form"},
                {"type": "category_count", "op": ">=", "value": 3},
                {"type": "has_budget", "value": True},
            ]},
            "level": "explicit", "missing_if_not": [], "weight": 90,
            "explain": "系列/形态/多品类/预算齐全 → 需求明确",
        },
    },
    {
        "type": "clarity", "name": "仅系列+形态 → 部分明确",
        "body": {
            "signal": {"type": "series_and_form"},
            "level": "partial", "missing_if_not": ["具体型号"], "weight": 50,
            "explain": "只给了系列和形态，缺具体型号",
        },
    },
    {
        "type": "clarity", "name": "无系列无形态 → 不明确",
        "body": {
            "signal": {"type": "no_series_no_form"},
            "level": "unclear", "missing_if_not": ["系列", "形态"], "weight": 30,
            "explain": "既无系列也无形态，需反问补齐",
        },
    },
    {
        "type": "clarity", "name": "无预算 → 部分明确",
        "body": {
            "signal": {"type": "no_budget"},
            "level": "partial", "missing_if_not": ["预算"], "weight": 40,
            "explain": "未提供预算，配件档次无法确定",
        },
    },
    {
        "type": "clarity", "name": "提到 CPU 却无 CPU 型号 → 部分明确",
        "body": {
            "signal": {"type": "no_model_in_category", "category": "CPU"},
            "level": "partial", "missing_if_not": ["CPU型号"], "weight": 45,
            "explain": "提到了 CPU 品类但没给具体型号",
        },
    },
    {
        "type": "clarity", "name": "提到 GPU 却无 GPU 型号 → 部分明确",
        "body": {
            "signal": {"type": "no_model_in_category", "category": "GPU"},
            "level": "partial", "missing_if_not": ["GPU型号"], "weight": 46,
            "explain": "提到了 GPU 品类但没给具体型号",
        },
    },
    {
        "type": "clarity", "name": "提到内存却无容量 → 部分明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "no_model_in_category", "category": "Memory"},
                {"type": "no_memory_capacity"},
            ]},
            "level": "partial", "missing_if_not": ["内存容量"], "weight": 44,
            "explain": "提到了内存品类但没解析到容量",
        },
    },

    {
        "type": "clarity", "name": "品类≥4 + 内存容量 → 明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "category_count", "op": ">=", "value": 4},
                {"type": "has_memory_capacity", "value": True},
            ]},
            "level": "explicit", "missing_if_not": [], "weight": 85,
            "explain": "4 个以上配件品类且有内存容量 → 明细清单，直接组 BOM",
        },
    },
    {
        "type": "clarity", "name": "品类≥4 + 型号 token → 明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "category_count", "op": ">=", "value": 4},
                {"type": "model_token_count", "op": ">=", "value": 1},
            ]},
            "level": "explicit", "missing_if_not": [], "weight": 84,
            "explain": "4 个以上配件品类且给出具体型号 → 明细清单，直接组 BOM",
        },
    },
    {
        "type": "clarity", "name": "型号 token ≥3 → 明确",
        "body": {
            "signal": {"type": "model_token_count", "op": ">=", "value": 3},
            "level": "explicit", "missing_if_not": [], "weight": 80,
            "explain": "贴了 3 个以上具体型号/规格 token → 需求明确",
        },
    },
    {
        "type": "clarity", "name": "品类≥3 + 内存容量 + 用途 → 明确",
        "body": {
            "signal": {"type": "combined", "rules": [
                {"type": "category_count", "op": ">=", "value": 3},
                {"type": "has_memory_capacity", "value": True},
                {"type": "has_usage", "value": True},
            ]},
            "level": "explicit", "missing_if_not": [], "weight": 75,
            "explain": "多品类 + 内存容量 + 明确用途 → 需求明确",
        },
    },
    # ── budget：预算区间 → 选配策略 ──
    {
        "type": "budget", "name": "经济型（8万以内）",
        "body": {
            "range": {"min": 0, "max": 80000, "currency": "CNY"},
            "strategy": {"representative_pick": "min_price", "label": "经济型"},
        },
    },
    {
        "type": "budget", "name": "均衡型（8-20万）",
        "body": {
            "range": {"min": 80000, "max": 200000, "currency": "CNY"},
            "strategy": {"representative_pick": "min_price", "label": "均衡"},
        },
    },
    {
        "type": "budget", "name": "高性能（20-50万）",
        "body": {
            "range": {"min": 200000, "max": 500000, "currency": "CNY"},
            "strategy": {"representative_pick": "max_price", "label": "高性能"},
        },
    },
    {
        "type": "budget", "name": "顶配（50万以上）",
        "body": {
            "range": {"min": 500000, "max": None, "currency": "CNY"},
            "strategy": {"representative_pick": "max_price", "label": "顶配"},
        },
    },
    {
        "type": "budget", "name": "无预算默认",
        "body": {
            "range": {"min": None, "max": None, "currency": "CNY"},
            "strategy": {"representative_pick": "min_price", "label": "默认"},
        },
    },

    # ── 选型规则目录：节点只引用，不内嵌 ──
    {"type": "cpu_mem_generation", "name": "KH50000 → DDR5", "body": {"pattern": "KH50000|KH-50000|KH5000", "mem_type": "DDR5"}},
    {"type": "cpu_mem_generation", "name": "KH40000/KX → DDR4", "body": {"pattern": "KH40000|KH4000|KX", "mem_type": "DDR4"}},
    {"type": "cpu_mem_generation", "name": "EPYC 9 → DDR5", "body": {"pattern": "EPYC 9", "mem_type": "DDR5"}},
    {"type": "cpu_mem_generation", "name": "EPYC 7 → DDR4", "body": {"pattern": "EPYC 7", "mem_type": "DDR4"}},
    {"type": "cpu_mem_generation", "name": "XEON 6 → DDR5", "body": {"pattern": "XEON 6", "mem_type": "DDR5"}},
    {"type": "cpu_mem_generation", "name": "XEON 1-4 → DDR4", "body": {"pattern": "XEON [1-4]", "mem_type": "DDR4"}},

    {"type": "category_alias", "name": "CPU 品类别名", "body": {"category": "CPU", "aliases": ["CPU", "处理器"]}},
    {"type": "category_alias", "name": "Memory 品类别名", "body": {"category": "Memory", "aliases": ["Memory", "内存", "内存条", "RAM"]}},
    {"type": "category_alias", "name": "HDD/SSD 品类别名", "body": {"category": "HDD/SSD", "aliases": ["HDD", "SSD", "硬盘", "Storage", "存储"]}},
    {"type": "category_alias", "name": "GPU 品类别名", "body": {"category": "GPU", "aliases": ["GPU", "显卡", "图形卡"]}},
    {"type": "category_alias", "name": "NIC 品类别名", "body": {"category": "NIC", "aliases": ["NIC", "网卡", "Network"]}},
    {"type": "category_alias", "name": "Raid card 品类别名", "body": {"category": "Raid card", "aliases": ["RAID", "Raid", "阵列卡"]}},
    {"type": "category_alias", "name": "Power 品类别名", "body": {"category": "Power", "aliases": ["PSU", "电源", "Power"]}},
    {"type": "category_alias", "name": "Fan 品类别名", "body": {"category": "Fan", "aliases": ["Fan", "风扇"]}},
    {"type": "category_alias", "name": "Heatsink 品类别名", "body": {"category": "Heatsink", "aliases": ["Heatsink", "散热器", "散热"]}},
    {"type": "category_alias", "name": "Cable 品类别名", "body": {"category": "Cable", "aliases": ["Cable", "线缆"]}},
    {"type": "category_alias", "name": "Rail 品类别名", "body": {"category": "Rail", "aliases": ["Rail", "导轨"]}},
    {"type": "category_alias", "name": "Backplane 品类别名", "body": {"category": "Backplane", "aliases": ["Backplane", "背板"]}},

    {"type": "platform_series_map", "name": "AMD/EPYC → Orion", "body": {"series": "Orion", "keywords": ["epyc", "amd", "orion", "霄龙", "猎户", "genoa", "9654", "9554", "9354", "9124", "9254", "9745"], "evidence": "AMD/EPYC 平台"}},
    {"type": "platform_series_map", "name": "兆芯/信创 → Polaris", "body": {"series": "Polaris", "keywords": ["kh", "kh50000", "kh-50000", "kh5000", "kh-5000", "兆芯", "zhaoxin", "开胜", "开先", "kx", "kx40000", "kx-40000", "信创"], "evidence": "兆芯/信创平台"}},
    {"type": "platform_series_map", "name": "Intel/Xeon → Intel", "body": {"series": "Intel", "keywords": ["xeon", "intel", "至强"], "evidence": "Intel 平台"}},
    {"type": "cpu_vendor_map", "name": "CPU: AMD/EPYC → Orion", "body": {"vendor": "amd", "series": "Orion", "pattern": r"AMD|EPYC", "flags": "i", "evidence": "AMD/EPYC 平台"}},
    {"type": "cpu_vendor_map", "name": "兆芯 → Polaris", "body": {"vendor": "zhaoxin", "series": "Polaris", "pattern": r"(?:^|[^A-Za-z0-9])(?:KH|KX|ZX)|兆芯|zhaoxin|开胜|开先", "flags": "i", "evidence": "Polaris 配兆芯"}},
    {"type": "cpu_vendor_map", "name": "Intel → Intel", "body": {"vendor": "intel", "series": "Intel", "pattern": r"INTEL|XEON", "flags": "i", "evidence": "Intel 平台"}},
    {"type": "cpu_vendor_map", "name": "海光", "body": {"vendor": "hygon", "series": "", "pattern": r"海光|hygon|C86", "flags": "i", "evidence": "海光 CPU 家族"}},
    {"type": "cpu_vendor_map", "name": "飞腾", "body": {"vendor": "phytium", "series": "", "pattern": r"飞腾|phytium|腾锐|腾云", "flags": "i", "evidence": "飞腾 CPU 家族"}},
    {"type": "cpu_vendor_map", "name": "鲲鹏", "body": {"vendor": "kunpeng", "series": "", "pattern": r"鲲鹏|kunpeng|\b920\b", "flags": "i", "evidence": "鲲鹏 CPU 家族"}},
    {"type": "cpu_vendor_map", "name": "龙芯", "body": {"vendor": "loongson", "series": "", "pattern": r"龙芯|loongson", "flags": "i", "evidence": "龙芯 CPU 家族"}},
    {"type": "gpu_brand_map", "name": "GPU 品牌词表", "body": {"nvidia": ["nvidia", "rtx", "geforce", "quadro", "tesla", "a100", "a800", "h100", "h200", "b100", "b200", "l40", "l20"], "amd": ["amd", "radeon", "r9700", "w7900", "mi300", "mi250", "mi210"]}},
    {"type": "spec_unit_patterns", "name": "规格单位正则", "body": {"gb": r"g(?:b)?", "tb": r"t(?:b)?", "mb": r"m(?:b)?", "pcs": r"(?:pcs?|颗|个)", "w": r"w(?:att)?", "rpm": r"rpm", "cores": r"(?:cores?|核|c)", "核": r"(?:cores?|核|c)", "mhz": r"m(?:hz)?", "ghz": r"g(?:hz)?"}},
    {"type": "power_calibration", "name": "功耗/电源推断校准", "body": {"sys_base_w": 260, "default_cpu_tdp": 280, "cpu_tdp_map": {"9654": 360, "9554": 360, "9754": 360, "9745": 360, "9174f": 320, "9454": 290, "9354": 280, "9534": 280, "9334": 280, "8434": 290, "9124": 200}, "mem_stick_w": 10, "mem_stick_w_by_cap": [[16, 8], [32, 10], [64, 15], [512, 20]], "sata_drive_w": 8, "nvme_drive_w": 15, "nic_w": 10, "raid_w": 15, "psu_standard_w": [1300, 1600, 2000, 2700, 3200], "high_tdp_gpus": ["H100", "A100", "H200", "B200", "B100", "L40", "MI300", "RTX PRO", "RTX 6000", "RTX 5090"], "high_tdp_threshold_w": 250, "gpu_tdp_by_model": {"R9700": 300, "W7900": 300, "L40": 300, "RTX 5090": 350}, "tiers": [{"min_gpu": 8, "high_tdp": True, "wattage": "2700"}, {"min_gpu": 1, "high_tdp": False, "wattage": "2000"}], "no_gpu_wattage": "1600"}},
    {"type": "type_alias", "name": "AI 类型别名", "body": {"keyword": "AI加速", "type_name": "AI / 加速计算服务器", "aliases": ["AI加速", "AI服务器", "AI训推", "算力", "AI推理", "AI", "加速计算"]}},
    {"type": "type_alias", "name": "通用计算类型别名", "body": {"keyword": "通用计算", "type_name": "通用计算服务器", "aliases": ["通用计算", "通用", "办公", "Web", "虚拟化基础", "计算"]}},
    {"type": "type_alias", "name": "存储类型别名", "body": {"keyword": "存储", "type_name": "存储服务器", "aliases": ["存储", "文件", "NAS", "备份"]}},

    {"type": "type_package", "name": "AI 机型套餐", "body": {"type_keyword": "AI", "categories": ["CPU", "GPU", "Memory", "HDD/SSD"], "mandatory_gpu": True, "gpu_overridable_by_exclusion": True, "ask_gpu": "auto"}},
    {"type": "type_package", "name": "存储机型套餐", "body": {"type_keyword": "存储", "categories": ["CPU", "Memory", "HDD/SSD", "Raid card"], "mandatory_storage": True}},
    {"type": "type_package", "name": "通用机型套餐", "body": {"type_keyword": "通用", "categories": ["CPU", "Memory", "HDD/SSD"]}},
    {"type": "type_package", "name": "国产化/信创套餐", "body": {"type_keyword": "国产化", "categories": ["CPU", "Memory", "HDD/SSD"], "compliance": "domestic_only", "platform_series": ["Polaris"]}},
    {"type": "type_package", "name": "AI 大模型套餐", "body": {"type_keyword": "大模型", "categories": ["CPU", "GPU", "Memory", "HDD/SSD"], "mandatory_gpu": True, "gpu_overridable_by_exclusion": True, "ask_gpu": "auto", "intent": "llm_inference"}},

    {"type": "spec_rule", "name": "CPU 默认 ≥16 核", "body": {"category": "CPU", "spec_key": "Cores", "op": ">=", "value": 16, "unit": "核"}},
    {"type": "spec_rule", "name": "内存默认 ≥16GB", "body": {"category": "Memory", "spec_key": "Capacity", "op": ">=", "value": 16, "unit": "GB"}},
    {"type": "spec_rule", "name": "GPU 默认 ≥16GB", "body": {"category": "GPU", "spec_key": "Capacity", "op": ">=", "value": 16, "unit": "GB"}},
    {"type": "spec_rule", "name": "硬盘默认 ≥480GB", "body": {"category": "HDD/SSD", "spec_key": "Capacity", "op": ">=", "value": 480, "unit": "GB"}},

    {"type": "raid_level_map", "name": "RAID 0/1/10 → 硬件阵列卡", "body": {"level": "RAID 0,1,10", "category": "Raid card", "prefer_models": ["9560", "9364"], "evidence": "明确 RAID 级别但未给型号 → 仍需硬件阵列卡"}},
    {"type": "raid_level_map", "name": "RAID 5/6 → 硬件阵列卡", "body": {"level": "RAID 5,6", "category": "Raid card", "prefer_models": ["9560", "9364"], "evidence": "RAID 5/6 需硬件阵列卡与缓存"}},

    {"type": "capacity_match", "name": "容量匹配默认策略", "body": {"strategy": "tolerance", "tolerance": 10}},
    {"type": "fallback_order", "name": "机型选型放宽顺序", "body": {"order": ["exact", "same_series", "same_form", "all"], "no_signal_strategy": "return_empty"}},
    {"type": "check_rule", "name": "方案自检默认项", "body": {"checks": {"plan_not_empty": True, "required_fields": True, "qty_reasonable": True}, "on_fail": "mark"}},

    {"type": "workload_map", "name": "70B 大模型 → 8卡 140G", "body": {"workload_keyword": "70B", "intent": "llm_inference", "total_vram_gb": 140, "gpu_count": 8}},
    {"type": "workload_map", "name": "Qwen-72B → 2卡 146G", "body": {"workload_keyword": "Qwen-72B", "intent": "llm_inference", "total_vram_gb": 146, "gpu_count": 2}},

    {"type": "compliance_map", "name": "国产化 → Polaris + 国产件", "body": {"domestic_only": True, "platform_series": ["Polaris"], "cpu_keywords": ["KH", "兆芯", "开胜"], "allowed_manufacturers": ["兆芯", "海光"], "excluded_manufacturers": ["AMD", "Intel", "NVIDIA"], "gpu_policy": "exclude_foreign"}},

    {"type": "model_action_phrases", "name": "机型选型用户意图词表", "body": {
        "auto_pick": ["你推荐", "你选", "随便", "都行", "听你的", "你定", "推荐一个"],
        "reselect": ["重选", "重新选", "换一台", "换机型", "再看", "别的机型"],
        "cancel": ["算了", "不要了", "取消", "中止", "结束", "退出"]
    }},
    {"type": "kp_action_phrases", "name": "配件选配用户意图词表", "body": {
        "cancel": ["算了", "不要了", "取消", "中止", "结束", "退出"],
        "reselect_model": ["重选机型", "重新选机型", "换机型", "换一台", "重新选服务器", "改机型"],
        "confirm": ["你推荐", "随便", "都行", "听你的", "你定", "推荐吧", "可以", "确认", "没问题", "继续", "就这个", "行", "好"]
    }},
]

class RequirementRuleRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    # ===== 规则 CRUD =====
    def list(self, type: Optional[str] = None, status: Optional[str] = None,
             domain: str = "requirement") -> List[dict]:
        q = self.session.query(RequirementRule)
        if domain:
            q = q.filter(RequirementRule.domain == domain)
        if type:
            q = q.filter(RequirementRule.type == type)
        if status:
            q = q.filter(RequirementRule.status == status)
        q = q.order_by(RequirementRule.type, RequirementRule.id)
        return [r.to_dict() for r in q.all()]

    def list_by_type(self, rule_type: str, status: str = "active") -> List[dict]:
        """pipeline 读取用：某 type 的生效规则（body 已解析）。"""
        return self.list(type=rule_type, status=status)

    def get(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        return r.to_dict() if r else None

    def create(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        body = data.get("body")
        scope = data.get("scope")
        rule = RequirementRule(
            domain=data.get("domain", "requirement"),
            type=data["type"],
            name=data["name"],
            scope=json.dumps(scope, ensure_ascii=False) if scope else None,
            body=json.dumps(body, ensure_ascii=False) if body is not None else "{}",
            status=data.get("status", "active"),
            version=1,
            hit_count=0,
            change_reason=data.get("change_reason"),
            description=data.get("description"),
            created_at=now,
            updated_at=now,
            created_by=operator,
            updated_by=operator,
        )
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule.to_dict()

    def update(self, rule_id: int, data: dict, operator: str = "system") -> Optional[dict]:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        if not r:
            return None
        now = datetime.now().isoformat()
        for k in ("type", "name", "status", "change_reason", "description"):
            if k in data and data[k] is not None:
                setattr(r, k, data[k])
        if "scope" in data:
            r.scope = json.dumps(data["scope"], ensure_ascii=False) if data["scope"] else None
        if "body" in data:
            r.body = json.dumps(data["body"], ensure_ascii=False) if data["body"] is not None else "{}"
        r.version = (r.version or 1) + 1
        r.updated_at = now
        r.updated_by = operator
        self.session.commit()
        self.session.refresh(r)
        return r.to_dict()

    def set_status(self, rule_id: int, status: str, operator: str = "system") -> Optional[dict]:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        if not r:
            return None
        r.status = status
        r.updated_at = datetime.now().isoformat()
        r.updated_by = operator
        self.session.commit()
        return r.to_dict()

    def delete(self, rule_id: int) -> bool:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        if not r:
            return False
        self.session.query(RequirementSample).filter(RequirementSample.rule_id == rule_id).delete()
        self.session.delete(r)
        self.session.commit()
        return True

    # ===== 命中计数（越跑越聪明） =====
    def record_hit(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        if not r:
            return None
        r.hit_count = (r.hit_count or 0) + 1
        r.last_hit_at = datetime.now().isoformat()
        self.session.commit()
        self.session.refresh(r)
        return {"id": r.id, "hit_count": r.hit_count, "last_hit_at": r.last_hit_at}

    def record_hits(self, rule_ids: list) -> int:
        """批量记录命中：执行链路一次提交多条规则（同 compatibility_rule_repo 模式）。"""
        ids = [int(i) for i in rule_ids if i]
        if not ids:
            return 0
        now = datetime.now().isoformat()
        self.session.query(RequirementRule).filter(RequirementRule.id.in_(ids)).update(
            {
                RequirementRule.hit_count: RequirementRule.hit_count + 1,
                RequirementRule.last_hit_at: now,
            },
            synchronize_session=False,
        )
        self.session.commit()
        return len(ids)

    def stats(self, rule_id: int) -> dict:
        r = self.session.query(RequirementRule).filter(RequirementRule.id == rule_id).first()
        if not r:
            return {"hit_count": 0, "last_hit_at": None}
        return {"hit_count": r.hit_count or 0, "last_hit_at": r.last_hit_at}

    # ===== 样本 CRUD =====
    def list_samples(self, rule_id: Optional[int] = None, enabled: Optional[bool] = None) -> List[dict]:
        q = self.session.query(RequirementSample)
        if rule_id is not None:
            q = q.filter(RequirementSample.rule_id == rule_id)
        if enabled is not None:
            q = q.filter(RequirementSample.enabled == enabled)
        q = q.order_by(RequirementSample.id.desc())
        return [s.to_dict() for s in q.all()]

    def add_sample(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        exp = data.get("expected_result")
        tags = data.get("tags")
        s = RequirementSample(
            rule_id=data["rule_id"],
            sample_text=data.get("sample_text"),
            expected_result=json.dumps(exp, ensure_ascii=False) if exp is not None else None,
            source=data.get("source", "manual"),
            tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            enabled=data.get("enabled", True),
            created_at=now, updated_at=now,
            created_by=operator, updated_by=operator,
        )
        self.session.add(s)
        self.session.commit()
        self.session.refresh(s)
        return s.to_dict()

    def update_sample(self, sample_id: int, data: dict, operator: str = "system") -> Optional[dict]:
        s = self.session.query(RequirementSample).filter(RequirementSample.id == sample_id).first()
        if not s:
            return None
        now = datetime.now().isoformat()
        for k in ("rule_id", "sample_text", "source", "enabled"):
            if k in data and data[k] is not None:
                setattr(s, k, data[k])
        if "expected_result" in data:
            s.expected_result = json.dumps(data["expected_result"], ensure_ascii=False) if data["expected_result"] is not None else None
        if "tags" in data:
            s.tags = json.dumps(data["tags"], ensure_ascii=False) if data["tags"] else None
        s.updated_at = now
        s.updated_by = operator
        self.session.commit()
        self.session.refresh(s)
        return s.to_dict()

    def delete_sample(self, sample_id: int) -> bool:
        s = self.session.query(RequirementSample).filter(RequirementSample.id == sample_id).first()
        if not s:
            return False
        self.session.delete(s)
        self.session.commit()
        return True

    def reset_to_defaults(self) -> int:
        """清空并重新 seed 默认规则（规则迭代后让用户一键更新到最新 seed）。"""
        try:
            self.session.query(RequirementSample).delete()
            self.session.query(RequirementRule).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.seed_default_if_empty()

    # ===== 旧思路清理（目录驱动引导上线后，workload/rebuttal 已废弃） =====
    # 按名称过时的规则也随启动清理（如"无用途→不明确"：目录引导下用途不再是反问字段）
    _OBSOLETE_RULE_NAMES = {"无用途 → 不明确"}

    def cleanup_obsolete_rules(self) -> int:
        """删除已废弃规则及其样本，幂等：无则删 0。
        1) 类型不在 clarity/budget 的（旧 rebuttal/workload——臆造选项反问）；
        2) 名称过时的 clarity 规则（_OBSOLETE_RULE_NAMES，目录驱动引导后语义失效）。
        保留只会继续误导判定，清掉让 rule 库与当前思路一致。"""
        keep = _VALID_TYPE
        deleted = 0
        for r in self.session.query(RequirementRule).all():
            obsolete = r.type not in keep or r.name in self._OBSOLETE_RULE_NAMES
            if not obsolete:
                continue
            self.session.query(RequirementSample).filter(
                RequirementSample.rule_id == r.id
            ).delete(synchronize_session=False)
            self.session.delete(r)
            deleted += 1
        if deleted:
            self.session.commit()
        return deleted


    # ===== Seed =====
    def seed_default_if_empty(self) -> int:
        existing = self.session.query(RequirementRule).count()
        if existing > 0:
            return 0
        now = datetime.now().isoformat()
        for item in DEFAULT_RULES:
            self.session.add(RequirementRule(
                domain="requirement",
                type=item["type"],
                name=item["name"],
                body=json.dumps(item["body"], ensure_ascii=False),
                status="active",
                version=1,
                hit_count=0,
                created_at=now, updated_at=now,
                created_by="seed", updated_by="seed",
            ))
        self.session.commit()
        return len(DEFAULT_RULES)

    def seed_missing_defaults(self) -> int:
        """按 name 非破坏补种 DEFAULT_RULES 新增项（不覆盖用户已有规则/命中计数）。
        规则迭代后新增的 clarity/rebuttal/budget 项随启动自动补上（与兼容规则同模式）。"""
        existing = {r.name for r in self.session.query(RequirementRule).all()}
        now = datetime.now().isoformat()
        added = 0
        for item in DEFAULT_RULES:
            if item["name"] in existing:
                continue
            self.session.add(RequirementRule(
                domain="requirement", type=item["type"], name=item["name"],
                body=json.dumps(item["body"], ensure_ascii=False),
                status="active", version=1, hit_count=0,
                created_at=now, updated_at=now, created_by="seed-missing", updated_by="seed-missing",
            ))
            added += 1
        if added:
            self.session.commit()
        return added

    def close(self):
        self.session.close()
