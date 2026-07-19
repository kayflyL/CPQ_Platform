"""config_schemes repo — 服务器页配置方案 / 无价 BOM 保存读取。"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class ConfigSchemeRepository:
    def list(self, model_id: Optional[int] = None) -> List[dict]:
        q = "SELECT id, name, model_id, created_at, payload FROM l6.config_schemes WHERE 1=1"
        p: dict = {}
        if model_id:
            q += " AND model_id=:mid"; p["mid"] = model_id
        q += " ORDER BY created_at DESC"
        with l6_engine.connect() as c:
            return [self._parse(dict(r)) for r in c.execute(text(q), p).mappings().all()]

    def get(self, scheme_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text("SELECT * FROM l6.config_schemes WHERE id=:id"),
                          {"id": scheme_id}).mappings().first()
        return self._parse(dict(r)) if r else None

    def insert(self, data: dict) -> int:
        d = {k: v for k, v in data.items() if k in {"name", "model_id", "payload"}}
        if "payload" in d and isinstance(d["payload"], (dict, list)):
            d["payload"] = json.dumps(d["payload"], ensure_ascii=False)
        cols = list(d.keys())
        q = f"INSERT INTO l6.config_schemes ({','.join(cols)}) VALUES ({','.join([':' + k for k in cols])}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def delete(self, scheme_id: int) -> bool:
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.config_schemes WHERE id=:id"), {"id": scheme_id})
        return True

    @staticmethod
    def _parse(r: dict) -> dict:
        if "payload" in r and isinstance(r["payload"], str):
            try:
                r["payload"] = json.loads(r["payload"])
            except Exception:
                pass
        return r
