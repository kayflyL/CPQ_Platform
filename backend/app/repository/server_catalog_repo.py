"""server_types / server_models repo — 服务器类型与机型目录。

机型是面向客户的产品实体：技术参数（form/bays/series）从关联的基准配置继承，
自身只承载产品级字段（name/use/description/image_url/lifecycle_status）。
原生 SQL，走 l6_engine（l6 schema）。
"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class ServerCatalogRepository:
    # 机型可写的字段白名单（form/bays 已移除——改由基准配置 JOIN 提供）
    _MODEL_FIELDS = {
        "name", "server_type_id", "use", "base_config_id", "sort_order",
        "description", "image_url", "lifecycle_status", "product_content",
    }

    # 服务器类型可写字段白名单
    _TYPE_FIELDS = {"name", "description", "sort_order", "showcase_config"}

    @staticmethod
    def _attach_base_config(row: dict) -> dict:
        """把 JOIN 来的 base_config_* 收进嵌套对象，删掉平铺前缀键。"""
        if not row:
            return row
        bc = None
        if row.get("base_config_id") is not None:
            bc = {
                "id": row.get("base_config_id"),
                "form": row.get("bc_form"),
                "bays": row.get("bc_bays"),
                "series": row.get("bc_series"),
                "name": row.get("bc_name"),
            }
        # 清掉 JOIN 临时前缀键
        for k in ("bc_form", "bc_bays", "bc_series", "bc_name"):
            row.pop(k, None)
        row["base_config"] = bc
        # JSONB 列（psycopg2 可能返回 str）归一化为 dict
        pc = row.get("product_content")
        if isinstance(pc, str):
            row["product_content"] = json.loads(pc)
        return row
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

    def update_type(self, type_id: int, updates: dict) -> bool:
        """更新服务器类型，包括 showcase_config"""
        f, v = [], {}
        for k, val in updates.items():
            if k not in self._TYPE_FIELDS:
                continue
            if k == "showcase_config" and isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
                f.append("showcase_config = CAST(:showcase_config AS jsonb)")
            else:
                f.append(f"{k}=:{k}")
            v[k] = val
        if not f:
            return False
        v["id"] = type_id
        q = f"UPDATE l6.server_types SET {','.join(f)} WHERE id=:id"
        with l6_engine.begin() as c:
            c.execute(text(q), v)
        return True

    # ---- 机型 ----
    def list_models(self, type_id: Optional[int] = None,
                    series: Optional[str] = None, form: Optional[str] = None) -> List[dict]:
        q = """
            SELECT m.*, bc.form AS bc_form, bc.bays AS bc_bays,
                   bc.series AS bc_series, bc.name AS bc_name
            FROM l6.server_models m
            LEFT JOIN l6.base_configs bc ON bc.id = m.base_config_id
            WHERE 1=1
        """
        p: dict = {}
        if type_id:
            q += " AND m.server_type_id=:t"
            p["t"] = type_id
        if series:
            q += " AND bc.series=:s"
            p["s"] = series
        if form:
            q += " AND bc.form=:f"
            p["f"] = form
        q += " ORDER BY m.sort_order, m.id"
        with l6_engine.connect() as c:
            return [self._attach_base_config(dict(r))
                    for r in c.execute(text(q), p).mappings().all()]

    def get_model(self, model_id: int) -> Optional[dict]:
        q = """
            SELECT m.*, bc.form AS bc_form, bc.bays AS bc_bays,
                   bc.series AS bc_series, bc.name AS bc_name
            FROM l6.server_models m
            LEFT JOIN l6.base_configs bc ON bc.id = m.base_config_id
            WHERE m.id=:id
        """
        with l6_engine.connect() as c:
            r = c.execute(text(q), {"id": model_id}).mappings().first()
        return self._attach_base_config(dict(r)) if r else None

    def insert_model(self, data: dict) -> int:
        d = {k: v for k, v in data.items() if k in self._MODEL_FIELDS}
        if "name" not in d:
            raise ValueError("name required")
        if "product_content" in d and isinstance(d["product_content"], (dict, list)):
            d["product_content"] = json.dumps(d["product_content"], ensure_ascii=False)
        cols = list(d.keys())
        col_list = ",".join(cols)
        val_list = ",".join(f"CAST(:{k} AS jsonb)" if k == "product_content" else f":{k}" for k in cols)
        q = f"INSERT INTO l6.server_models ({col_list}) VALUES ({val_list}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def update_model(self, model_id: int, updates: dict) -> bool:
        f, v = [], {}
        for k, val in updates.items():
            if k not in self._MODEL_FIELDS:
                continue
            if k == "product_content" and isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
                f.append("product_content = CAST(:product_content AS jsonb)")
            else:
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
