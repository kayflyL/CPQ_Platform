"""Repository for rules.strategies + rules.strategy_usage_log."""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.strategy import Strategy, StrategyUsageLog


class StrategyRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def list(self, domain: Optional[str] = None, status: Optional[str] = None,
             type: Optional[str] = None) -> List[dict]:
        q = self.session.query(Strategy)
        if domain:
            q = q.filter(Strategy.domain == domain)
        if status:
            q = q.filter(Strategy.status == status)
        if type:
            q = q.filter(Strategy.type == type)
        q = q.order_by(Strategy.domain, Strategy.id)
        return [s.to_dict() for s in q.all()]

    def get(self, strategy_id: int) -> Optional[dict]:
        s = self.session.query(Strategy).filter(Strategy.id == strategy_id).first()
        return s.to_dict() if s else None

    def create(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        body = data.get("body")
        scope = data.get("scope")
        strat = Strategy(
            domain=data["domain"],
            type=data["type"],
            name=data["name"],
            scope=json.dumps(scope, ensure_ascii=False) if scope else None,
            body=json.dumps(body, ensure_ascii=False) if body is not None else "{}",
            status=data.get("status", "draft"),
            version=1,
            change_reason=data.get("change_reason"),
            description=data.get("description"),
            created_at=now,
            updated_at=now,
            created_by=operator,
            updated_by=operator,
        )
        self.session.add(strat)
        self.session.commit()
        self.session.refresh(strat)
        return strat.to_dict()

    def update(self, strategy_id: int, data: dict, operator: str = "system") -> Optional[dict]:
        s = self.session.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not s:
            return None
        now = datetime.now().isoformat()
        for k in ("domain", "type", "name", "status", "change_reason", "description"):
            if k in data and data[k] is not None:
                setattr(s, k, data[k])
        if "scope" in data:
            s.scope = json.dumps(data["scope"], ensure_ascii=False) if data["scope"] else None
        if "body" in data:
            s.body = json.dumps(data["body"], ensure_ascii=False) if data["body"] is not None else "{}"
        s.version = (s.version or 1) + 1
        s.updated_at = now
        s.updated_by = operator
        self.session.commit()
        self.session.refresh(s)
        return s.to_dict()

    def set_status(self, strategy_id: int, status: str, operator: str = "system") -> Optional[dict]:
        s = self.session.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not s:
            return None
        s.status = status
        s.updated_at = datetime.now().isoformat()
        s.updated_by = operator
        self.session.commit()
        return s.to_dict()

    def delete(self, strategy_id: int) -> bool:
        s = self.session.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not s:
            return False
        self.session.query(StrategyUsageLog).filter(
            StrategyUsageLog.strategy_id == strategy_id
        ).delete()
        self.session.delete(s)
        self.session.commit()
        return True

    # ===== 引用埋点 =====
    def record_usage(self, strategy_id: int, version: Optional[int] = None,
                     ref_type: Optional[str] = None, ref_id: Optional[str] = None,
                     operator: str = "system") -> dict:
        log = StrategyUsageLog(
            strategy_id=strategy_id,
            strategy_version=version,
            ref_type=ref_type,
            ref_id=ref_id,
            operator=operator,
            referenced_at=datetime.now().isoformat(),
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return {"id": log.id}

    def usage_stats(self, strategy_id: int) -> dict:
        logs = self.session.query(StrategyUsageLog).filter(
            StrategyUsageLog.strategy_id == strategy_id
        ).all()
        if not logs:
            return {"count": 0, "last_ref": None}
        return {
            "count": len(logs),
            "last_ref": max(l.referenced_at for l in logs if l.referenced_at),
        }

    def close(self):
        self.session.close()
