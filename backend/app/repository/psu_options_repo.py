"""电源选项 Repository — l6.l6_psu_options"""
from sqlalchemy import text
from app.models.base import l6_engine


class PsuOptionsRepository:
    def __init__(self):
        self.engine = l6_engine

    def list_options(self, series: str = None) -> list:
        """列出电源选项"""
        with self.engine.connect() as c:
            if series:
                rows = c.execute(text("""
                    SELECT psu_id, wattage, pn, part_name, description, unit_price,
                           applicable_chassis, note, sort_order
                    FROM l6.l6_psu_options
                    WHERE applicable_chassis IS NULL OR applicable_chassis LIKE :series
                    ORDER BY sort_order
                """), {"series": f'%"{series}"%'}).mappings().all()
            else:
                rows = c.execute(text("""
                    SELECT psu_id, wattage, pn, part_name, description, unit_price,
                           applicable_chassis, note, sort_order
                    FROM l6.l6_psu_options
                    ORDER BY sort_order
                """)).mappings().all()
        return [dict(r) for r in rows]
