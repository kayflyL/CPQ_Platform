"""server_3d_models repo — 服务器3D模型登记(原生SQL,走 l6_engine,l6 schema)。
绑定关系:server_3d_model_bindings 多对多(一个3D模型可绑多台机型,绑定即上架)。"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize(data: dict) -> dict:
    """layout_config 列是 TEXT:前端可能传对象,统一序列化成JSON字符串。"""
    out = dict(data)
    if out.get("layout_config") is not None and not isinstance(out["layout_config"], str):
        out["layout_config"] = json.dumps(out["layout_config"], ensure_ascii=False)
    return out


class Server3dModelRepository:

    _FIELDS = {"name", "layout_config", "kind", "part_type"}

    def _with_bindings(self, c, rows: List[dict]) -> List[dict]:
        """按行集合批量取绑定机型id,填进每行 model_ids。"""
        if not rows:
            return rows
        ids = [r["id"] for r in rows]
        rel = c.execute(text(
            "SELECT model_3d_id, model_id FROM l6.server_3d_model_bindings WHERE model_3d_id = ANY(:ids) ORDER BY model_id"
        ), {"ids": ids}).all()
        mapping: dict = {}
        for m3d, mid in rel:
            mapping.setdefault(m3d, []).append(mid)
        for r in rows:
            r["model_ids"] = mapping.get(r["id"], [])
        return rows

    def _row_to_dict(self, r, bindings: List[int]) -> dict:
        out = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        out["model_ids"] = bindings
        return out

    def list(self) -> List[dict]:
        with l6_engine.connect() as c:
            rows = [dict(x._mapping) for x in c.execute(text(
                "SELECT * FROM l6.server_3d_models ORDER BY id"
            )).all()]
            self._with_bindings(c, rows)
        return rows

    def get(self, id_: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text(
                "SELECT * FROM l6.server_3d_models WHERE id=:id"
            ), {"id": id_}).first()
            if not r:
                return None
            out = self._row_to_dict(r, [])
            self._with_bindings(c, [out])
        return out

    def get_by_model(self, model_id: int) -> Optional[dict]:
        """配置页反查:该机型绑定着的3D整机模型(多个取最新登记的一条;部件模型不参与绑定)。"""
        with l6_engine.connect() as c:
            r = c.execute(text(
                """
                SELECT m.* FROM l6.server_3d_models m
                JOIN l6.server_3d_model_bindings b ON b.model_3d_id = m.id
                WHERE b.model_id = :mid AND COALESCE(m.kind, 'machine') = 'machine'
                ORDER BY m.id DESC LIMIT 1
                """
            ), {"mid": model_id}).first()
            if not r:
                return None
            out = self._row_to_dict(r, [model_id])
        return out

    def set_bindings(self, id_: int, model_ids: List[int]) -> None:
        """整表替换该3D模型的机型绑定(绑定即上架)。"""
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.server_3d_model_bindings WHERE model_3d_id=:id"), {"id": id_})
            for mid in model_ids:
                c.execute(text(
                    "INSERT INTO l6.server_3d_model_bindings (model_3d_id, model_id) VALUES (:m3d, :mid) ON CONFLICT DO NOTHING"
                ), {"m3d": id_, "mid": mid})

    def bindings_of(self, id_: int) -> List[int]:
        with l6_engine.connect() as c:
            return [x[0] for x in c.execute(text(
                "SELECT model_id FROM l6.server_3d_model_bindings WHERE model_3d_id=:id ORDER BY model_id"
            ), {"id": id_}).all()]

    def update(self, id_: int, data: dict, model_ids: Optional[List[int]] = None) -> None:
        fields = {k: v for k, v in _normalize(data).items() if k in self._FIELDS}
        fields["updated_at"] = _now()
        with l6_engine.begin() as c:
            if fields:
                sets = ", ".join(f"{k}=:{k}" for k in fields)
                fields["id"] = id_
                c.execute(text(f"UPDATE l6.server_3d_models SET {sets} WHERE id=:id"), fields)
            if model_ids is not None:
                c.execute(text("DELETE FROM l6.server_3d_model_bindings WHERE model_3d_id=:id"), {"id": id_})
                for mid in model_ids:
                    c.execute(text(
                        "INSERT INTO l6.server_3d_model_bindings (model_3d_id, model_id) VALUES (:m3d, :mid) ON CONFLICT DO NOTHING"
                    ), {"m3d": id_, "mid": mid})

    def delete(self, id_: int) -> None:
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.server_3d_model_bindings WHERE model_3d_id=:id"), {"id": id_})
            c.execute(text("DELETE FROM l6.server_3d_models WHERE id=:id"), {"id": id_})
