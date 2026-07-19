"""bom_templates repo — 左栏 L6 配置单的机型族"行骨架"模板。

原生 SQL，走 l6_engine（schema=l6）。rows 是有序行类型 JSONB。
"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class BomTemplateRepository:

    def list(self) -> List[dict]:
        with l6_engine.connect() as c:
            rows = c.execute(text(
                "SELECT id, name, rows, sort_order FROM l6.bom_templates ORDER BY sort_order"
            )).mappings().all()
        return [self._row(r) for r in rows]

    def get(self, template_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text(
                "SELECT id, name, rows, sort_order FROM l6.bom_templates WHERE id=:id"
            ), {"id": template_id}).mappings().first()
        return self._row(r) if r else None

    def get_for_base_config(self, base_config_id: int) -> Optional[dict]:
        """取某 base_config 关联的模板（含 rows）。base_config 未关联则返回 None。"""
        with l6_engine.connect() as c:
            r = c.execute(text("""
                SELECT t.id, t.name, t.rows, t.sort_order
                FROM l6.base_configs bc
                JOIN l6.bom_templates t ON bc.bom_template_id = t.id
                WHERE bc.id = :cid
            """), {"cid": base_config_id}).mappings().first()
        return self._row(r) if r else None

    def count_base_configs(self, template_id: int) -> int:
        """统计有多少 base_config 在用此模板（编辑前提示共用影响）"""
        with l6_engine.connect() as c:
            return c.execute(text(
                "SELECT COUNT(*) FROM l6.base_configs WHERE bom_template_id = :tid"
            ), {"tid": template_id}).scalar() or 0

    def create(self, name: str, rows: list, sort_order: int = 0) -> int:
        with l6_engine.begin() as c:
            return c.execute(text("""
                INSERT INTO l6.bom_templates (name, rows, sort_order)
                VALUES (:name, CAST(:rows AS JSONB), :sort_order) RETURNING id
            """), {"name": name, "rows": json.dumps(rows, ensure_ascii=False), "sort_order": sort_order}).scalar()

    def update(self, template_id: int, name: Optional[str] = None, rows: Optional[list] = None) -> bool:
        f, v = [], {"id": template_id}
        if name is not None:
            f.append("name = :name"); v["name"] = name
        if rows is not None:
            f.append("rows = CAST(:rows AS JSONB)"); v["rows"] = json.dumps(rows, ensure_ascii=False)
        if not f:
            return False
        with l6_engine.begin() as c:
            c.execute(text(f"UPDATE l6.bom_templates SET {','.join(f)} WHERE id = :id"), v)
        return True

    def delete(self, template_id: int) -> bool:
        with l6_engine.begin() as c:
            c.execute(text("UPDATE l6.base_configs SET bom_template_id = NULL WHERE bom_template_id = :tid"),
                      {"tid": template_id})
            c.execute(text("DELETE FROM l6.bom_templates WHERE id = :id"), {"id": template_id})
        return True

    def _row(self, r) -> dict:
        d = dict(r)
        if isinstance(d.get("rows"), str):
            try:
                d["rows"] = json.loads(d["rows"])
            except Exception:
                d["rows"] = []
        return d
