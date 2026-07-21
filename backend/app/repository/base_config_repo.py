"""base_configs + base_config_parts repo — 基准配置（引用 parts_master）。

对应管理面「基准配置组装」。底盘件清单 JOIN parts_master 取 name/price/specs。
原生 SQL，走 l6_engine。
"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class BaseConfigRepository:
    def list(self, series: Optional[str] = None, form: Optional[str] = None,
             bays: Optional[int] = None, server_type_id: Optional[int] = None) -> List[dict]:
        q = "SELECT * FROM l6.base_configs WHERE 1=1"
        p: dict = {}
        if series:
            q += " AND series=:s"; p["s"] = series
        if form:
            q += " AND form=:f"; p["f"] = form
        if bays:
            q += " AND bays=:b"; p["b"] = bays
        if server_type_id:
            q += " AND server_type_id=:t"; p["t"] = server_type_id
        q += " ORDER BY sort_order"
        # 一次性聚合所有 config 的 料件数 + 合计价，避免 N+1
        agg_sql = """
            SELECT p.config_id,
                   COALESCE(SUM(p.quantity), 0) AS parts_count,
                   COALESCE(SUM(COALESCE(m.unit_price, 0) * p.quantity), 0) AS total_price
            FROM l6.base_config_parts p
            LEFT JOIN l6.parts_master m ON p.pn = m.pn
            GROUP BY p.config_id
        """
        with l6_engine.connect() as c:
            configs = [dict(r) for r in c.execute(text(q), p).mappings().all()]
            aggs = {r["config_id"]: r for r in c.execute(text(agg_sql)).mappings().all()}
        for cfg in configs:
            a = aggs.get(cfg["id"])
            cfg["parts_count"] = int(a["parts_count"]) if a else 0
            cfg["total_price"] = float(a["total_price"]) if a else 0.0
        return configs

    def get(self, config_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text("SELECT * FROM l6.base_configs WHERE id=:id"),
                          {"id": config_id}).mappings().first()
        return dict(r) if r else None

    def get_with_parts(self, config_id: int) -> Optional[dict]:
        cfg = self.get(config_id)
        if not cfg:
            return None
        cfg["parts"] = self.get_parts(config_id)
        return cfg

    def get_parts(self, config_id: int) -> List[dict]:
        q = """SELECT p.id, p.config_id, p.pn, p.quantity, p.locked, p.sort_order,
                      m.name, m.category, m.unit_price, m.specs
               FROM l6.base_config_parts p
               JOIN l6.parts_master m ON p.pn = m.pn
               WHERE p.config_id=:cid ORDER BY p.sort_order"""
        with l6_engine.connect() as c:
            rows = c.execute(text(q), {"cid": config_id}).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("specs"), str):
                try:
                    d["specs"] = json.loads(d["specs"])
                except Exception:
                    pass
            out.append(d)
        return out

    def insert(self, data: dict) -> int:
        allowed = {"name", "server_type_id", "series", "model", "form", "bays",
                   "bp_tri_pn", "bp_dc_pn", "gpu_arch_default", "sort_order", "bom_template_id"}
        d = {k: v for k, v in data.items() if k in allowed}
        if "name" not in d:
            raise ValueError("name required")
        cols = list(d.keys())
        q = f"INSERT INTO l6.base_configs ({','.join(cols)}) VALUES ({','.join([':' + k for k in cols])}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def update(self, config_id: int, updates: dict) -> bool:
        allowed = {"name", "server_type_id", "series", "model", "form", "bays",
                   "bp_tri_pn", "bp_dc_pn", "gpu_arch_default", "sort_order", "bom_template_id"}
        f, v = [], {}
        for k, val in updates.items():
            if k in allowed:
                f.append(f"{k}=:{k}")
                v[k] = val
        if not f:
            return False
        v["id"] = config_id
        q = f"UPDATE l6.base_configs SET {','.join(f)} WHERE id=:id"
        with l6_engine.begin() as c:
            c.execute(text(q), v)
        return True

    def delete(self, config_id: int) -> bool:
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.base_config_parts WHERE config_id=:id"), {"id": config_id})
            c.execute(text("DELETE FROM l6.base_configs WHERE id=:id"), {"id": config_id})
        return True

    def set_parts(self, config_id: int, parts: List[dict]) -> bool:
        """整体替换某 config 的底盘件清单。parts: [{pn, quantity, locked, sort_order}]"""
        with l6_engine.begin() as c:
            c.execute(text("DELETE FROM l6.base_config_parts WHERE config_id=:cid"),
                      {"cid": config_id})
            for p in parts:
                d = {"config_id": config_id, "pn": p["pn"],
                     "quantity": p.get("quantity", 1), "locked": p.get("locked", True),
                     "sort_order": p.get("sort_order", 0)}
                c.execute(text("""INSERT INTO l6.base_config_parts
                    (config_id, pn, quantity, locked, sort_order)
                    VALUES (:config_id, :pn, :quantity, :locked, :sort_order)"""), d)
        return True
