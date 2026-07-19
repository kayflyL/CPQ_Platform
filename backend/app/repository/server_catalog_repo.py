"""server_types / server_models repo — 服务器类型与机型目录。

对应配置面的「选机型」入口。卡片只展示 name/form/bays/use（不显芯片型号与背板）。
原生 SQL，走 l6_engine（l6 schema）。
"""
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class ServerCatalogRepository:
    # ---- 服务器类型 ----
    def list_types(self) -> List[dict]:
        with l6_engine.connect() as c:
            return [dict(r) for r in c.execute(
                text("SELECT * FROM l6.server_types ORDER BY sort_order")
            ).mappings().all()]

    def get_type(self, type_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text("SELECT * FROM l6.server_types WHERE id=:id"),
                          {"id": type_id}).mappings().first()
        return dict(r) if r else None

    def insert_type(self, data: dict) -> int:
        d = {k: v for k, v in data.items() if k in {"name", "description", "sort_order"}}
        if "name" not in d:
            raise ValueError("name required")
        cols = list(d.keys())
        q = f"INSERT INTO l6.server_types ({','.join(cols)}) VALUES ({','.join([':' + k for k in cols])}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def delete_type(self, type_id: int) -> bool:
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.server_types WHERE id=:id"), {"id": type_id})
        return True

    # ---- 机型 ----
    def list_models(self, type_id: Optional[int] = None) -> List[dict]:
        q = "SELECT * FROM l6.server_models WHERE 1=1"
        p: dict = {}
        if type_id:
            q += " AND server_type_id=:t"
            p["t"] = type_id
        q += " ORDER BY sort_order"
        with l6_engine.connect() as c:
            return [dict(r) for r in c.execute(text(q), p).mappings().all()]

    def get_model(self, model_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text("SELECT * FROM l6.server_models WHERE id=:id"),
                          {"id": model_id}).mappings().first()
        return dict(r) if r else None

    def insert_model(self, data: dict) -> int:
        d = {k: v for k, v in data.items()
             if k in {"name", "server_type_id", "form", "bays", "use", "base_config_id", "sort_order"}}
        if "name" not in d:
            raise ValueError("name required")
        cols = list(d.keys())
        q = f"INSERT INTO l6.server_models ({','.join(cols)}) VALUES ({','.join([':' + k for k in cols])}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def update_model(self, model_id: int, updates: dict) -> bool:
        allowed = {"name", "server_type_id", "form", "bays", "use", "base_config_id", "sort_order"}
        f, v = [], {}
        for k, val in updates.items():
            if k in allowed:
                f.append(f"{k}=:{k}")
                v[k] = val
        if not f:
            return False
        v["id"] = model_id
        q = f"UPDATE l6.server_models SET {','.join(f)} WHERE id=:id"
        with l6_engine.begin() as c:
            c.execute(text(q), v)
        return True

    def delete_model(self, model_id: int) -> bool:
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.server_models WHERE id=:id"), {"id": model_id})
        return True
