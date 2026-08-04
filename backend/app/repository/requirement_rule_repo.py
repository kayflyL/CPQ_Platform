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

    # ===== 旧思路清理（目录驱动引导上线后，workload/rebuttal 已废弃） =====
    # 按名称过时的规则也随启动清理（如"无用途→不明确"：目录引导下用途不再是反问字段）
    _OBSOLETE_RULE_NAMES = {"无用途 → 不明确"}

    def cleanup_obsolete_rules(self) -> int:
        """删除已废弃规则及其样本，幂等：无则删 0。
        1) 类型不在 clarity/budget 的（旧 rebuttal/workload——臆造选项反问）；
        2) 名称过时的 clarity 规则（_OBSOLETE_RULE_NAMES，目录驱动引导后语义失效）。
        保留只会继续误导判定，清掉让 rule 库与当前思路一致。"""
        keep = {"clarity", "budget"}
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
