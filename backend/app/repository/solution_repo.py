"""Repository for rules.solutions."""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.solution import Solution


def _j(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


class SolutionRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def list(self, scene_key: Optional[str] = None) -> List[dict]:
        q = self.session.query(Solution)
        if scene_key:
            q = q.filter(Solution.scene_key == scene_key)
        q = q.order_by(Solution.scene_key, Solution.id)
        return [s.to_dict() for s in q.all()]

    def get_by_key(self, key: str) -> Optional[dict]:
        s = self.session.query(Solution).filter(Solution.key == key).first()
        return s.to_dict() if s else None

    def get(self, solution_id: int) -> Optional[dict]:
        s = self.session.query(Solution).filter(Solution.id == solution_id).first()
        return s.to_dict() if s else None

    def create(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        sol = Solution(
            key=data["key"],
            scene_key=data["scene_key"],
            scene=data["scene"],
            title=data["title"],
            sub=data.get("sub"),
            features=_j(data.get("features")),
            intro=data.get("intro"),
            content_md=data.get("content_md"),
            platforms=_j(data.get("platforms")),
            created_at=now,
            updated_at=now,
        )
        self.session.add(sol)
        self.session.commit()
        self.session.refresh(sol)
        return sol.to_dict()

    def update(self, key: str, data: dict, operator: str = "system") -> Optional[dict]:
        sol = self.session.query(Solution).filter(Solution.key == key).first()
        if not sol:
            return None
        now = datetime.now().isoformat()
        for k in ("key", "scene_key", "scene", "title", "sub", "intro", "content_md"):
            if k in data:
                setattr(sol, k, data[k])
        for k in ("features", "platforms"):
            if k in data:
                setattr(sol, k, _j(data.get(k)))
        sol.updated_at = now
        self.session.commit()
        self.session.refresh(sol)
        return sol.to_dict()

    def delete(self, key: str) -> bool:
        sol = self.session.query(Solution).filter(Solution.key == key).first()
        if not sol:
            return False
        self.session.delete(sol)
        self.session.commit()
        return True

    def close(self):
        self.session.close()
