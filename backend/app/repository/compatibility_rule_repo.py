"""Compatibility rule repository — 兼容性规则引擎 CRUD（schema=rules）。

声明式 WHEN→THEN 规则，type: require/exclude/derive/filter/recommend。
规则本体住 rules.compatibility_rules（DB 唯一来源，无代码种子）；
body schema 与寻址约定见 docs/frontend-pages/strategies/strategies.md 与 selection_engine 模块注释。
"""
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.base import Rules_SessionLocal
from app.models.compatibility_rule import CompatibilityRule


class CompatibilityRuleRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    # ===== 规则 CRUD =====
    def list(self, type: Optional[str] = None, status: Optional[str] = None,
             domain: str = "selection", category: Optional[str] = None) -> List[dict]:
        q = self.session.query(CompatibilityRule)
        if domain:
            q = q.filter(CompatibilityRule.domain == domain)
        if type:
            q = q.filter(CompatibilityRule.type == type)
        if status:
            q = q.filter(CompatibilityRule.status == status)
        if category:
            q = q.filter(CompatibilityRule.category == category)
        q = q.order_by(CompatibilityRule.category, CompatibilityRule.type, CompatibilityRule.id)
        return [r.to_dict() for r in q.all()]

    def list_by_type(self, rule_type: str, status: str = "active") -> List[dict]:
        """执行器读取用：某 type 的生效规则（body 已解析）。"""
        return self.list(type=rule_type, status=status)

    def get(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        return r.to_dict() if r else None

    def create(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        body = data.get("body")
        scope = data.get("scope")
        rule = CompatibilityRule(
            domain=data.get("domain", "selection"),
            type=data["type"],
            category=data.get("category"),
            name=data["name"],
            scope=json.dumps(scope, ensure_ascii=False) if scope else None,
            regions=json.dumps(data.get("regions") or [], ensure_ascii=False),
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
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        now = datetime.now().isoformat()
        for k in ("type", "name", "status", "change_reason", "description"):
            if k in data and data[k] is not None:
                setattr(r, k, data[k])
        # category 允许清空（空串/None → 未分类），故不并入上面的非空守卫
        if "category" in data:
            cv = data["category"]
            r.category = cv.strip() if isinstance(cv, str) and cv.strip() else None
        if "scope" in data:
            r.scope = json.dumps(data["scope"], ensure_ascii=False) if data["scope"] else None
        if "regions" in data:
            r.regions = json.dumps(data["regions"] or [], ensure_ascii=False)
        if "body" in data:
            r.body = json.dumps(data["body"], ensure_ascii=False) if data["body"] is not None else "{}"
        r.version = (r.version or 1) + 1
        r.updated_at = now
        r.updated_by = operator
        self.session.commit()
        self.session.refresh(r)
        return r.to_dict()

    def set_status(self, rule_id: int, status: str, operator: str = "system") -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        r.status = status
        r.updated_at = datetime.now().isoformat()
        r.updated_by = operator
        self.session.commit()
        return r.to_dict()

    def delete(self, rule_id: int) -> bool:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return False
        self.session.delete(r)
        self.session.commit()
        return True

    # ===== 命中计数（越跑越聪明） =====
    def record_hit(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        r.hit_count = (r.hit_count or 0) + 1
        r.last_hit_at = datetime.now().isoformat()
        self.session.commit()
        self.session.refresh(r)
        return {"id": r.id, "hit_count": r.hit_count, "last_hit_at": r.last_hit_at}


    def record_hits(self, rule_ids: list) -> int:
        """批量命中计数（推理管线按方案跑规则后一次提交；单条走 record_hit）。"""
        if not rule_ids:
            return 0
        now = datetime.now().isoformat()
        rows = self.session.query(CompatibilityRule).filter(CompatibilityRule.id.in_(rule_ids)).all()
        n = 0
        for r in rows:
            r.hit_count = (r.hit_count or 0) + 1
            r.last_hit_at = now
            n += 1
        if n:
            self.session.commit()
        return n
    def stats(self, rule_id: int) -> dict:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return {"hit_count": 0, "last_hit_at": None}
        return {"hit_count": r.hit_count or 0, "last_hit_at": r.last_hit_at}

    def close(self):
        self.session.close()
