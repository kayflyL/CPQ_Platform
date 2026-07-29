"""Repository for rules.requirement_rules + rules.requirement_samples.

照 strategy_repo.py 模式。加 list_by_type / record_hit / sample CRUD / seed_default_if_empty。
"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.requirement_rule import RequirementRule, RequirementSample


# ===== 默认规则 seed（三层兜底的最底层常量也复用这套结构） =====
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
        "type": "clarity", "name": "无用途 → 不明确",
        "body": {
            "signal": {"type": "no_usage"},
            "level": "unclear", "missing_if_not": ["用途"], "weight": 35,
            "explain": "未说明用途场景，无法定向选型",
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
    # ── rebuttal：反问话术 ──
    {
        "type": "rebuttal", "name": "缺型号反问",
        "body": {
            "trigger_field": "具体型号", "priority": 90,
            "question": "您提到 {series} {form}，方便告诉我具体型号吗？比如 {example}。",
            "example_by_series": {
                "Orion": "AMD EPYC 9554",
                "Intel": "Intel Xeon Gold 6348",
                "Polaris": "NVIDIA HGX H100",
            },
            "example_default": "具体型号或规格",
            "options": [],
            "fallback": "请补充您需要的服务器型号。",
        },
    },
    {
        "type": "rebuttal", "name": "缺预算反问",
        "body": {
            "trigger_field": "预算", "priority": 50,
            "question": "这次采购的大致预算范围是？",
            "options": ["5万以内", "5-10万", "10-30万", "30万以上", "不限预算"],
            "fallback": "请补充预算范围。",
        },
    },
    {
        "type": "rebuttal", "name": "缺用途反问",
        "body": {
            "trigger_field": "用途", "priority": 80,
            "question": "这套配置主要用于什么场景？",
            "options": ["AI训练/推理", "虚拟化/云", "数据库/OLTP", "存储/备份", "通用计算"],
            "fallback": "请描述主要用途。",
        },
    },
    {
        "type": "rebuttal", "name": "缺系列反问",
        "body": {
            "trigger_field": "系列", "priority": 70,
            "question": "有没有倾向的产品系列或平台？",
            "options": ["Orion（AMD）", "Intel 平台", "Polaris", "工作站", "不确定/你推荐"],
            "fallback": "请告知倾向的系列或平台。",
        },
    },
    {
        "type": "rebuttal", "name": "缺形态反问",
        "body": {
            "trigger_field": "形态", "priority": 60,
            "question": "机箱形态有要求吗？",
            "options": ["2U 机架", "4U 塔式", "1U 机架", "高密度", "不确定"],
            "fallback": "请告知机箱形态要求。",
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

    def close(self):
        self.session.close()
