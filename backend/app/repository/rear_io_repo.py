"""后面板配置 Repository — l6.l6_rear_panel_items"""
import json
from sqlalchemy import text
from app.models.base import l6_engine


class RearIORepository:
    def __init__(self):
        self.engine = l6_engine

    def list_options(self, series: str = None) -> list:
        """列出后面板选项，按 io_slot + sort_order 排序。可按系列过滤。"""
        with self.engine.connect() as c:
            if series:
                rows = c.execute(text("""
                    SELECT item_id, io_slot, option_type, pn, part_name, description,
                           unit_price, quantity, applicable_chassis, applicable_backplane, note, sort_order
                    FROM l6.l6_rear_panel_items
                    WHERE applicable_chassis IS NULL OR applicable_chassis LIKE :series
                    ORDER BY io_slot, sort_order
                """), {"series": f'%"{series}"%'}).mappings().all()
            else:
                rows = c.execute(text("""
                    SELECT item_id, io_slot, option_type, pn, part_name, description,
                           unit_price, quantity, applicable_chassis, applicable_backplane, note, sort_order
                    FROM l6.l6_rear_panel_items
                    ORDER BY io_slot, sort_order
                """)).mappings().all()
        return [dict(r) for r in rows]

    def get_slot_options(self, slot: str, series: str = None) -> list:
        """获取指定槽位的选项列表，按 option_type 分组。"""
        all_items = self.list_options(series)
        slot_items = [i for i in all_items if i["io_slot"] == slot]
        # 按 option_type 分组
        groups = {}
        for item in slot_items:
            ot = item["option_type"]
            if ot not in groups:
                groups[ot] = {
                    "option_type": ot,
                    "items": [],
                    "total_price": 0
                }
            groups[ot]["items"].append(item)
            groups[ot]["total_price"] += float(item["unit_price"] or 0) * item["quantity"]
        return list(groups.values())

    def get_all_slots(self, series: str = None) -> dict:
        """获取所有槽位的选项，返回 {slot: [options]} 结构。"""
        all_items = self.list_options(series)
        slots = {}
        for item in all_items:
            slot = item["io_slot"]
            if slot not in slots:
                slots[slot] = []
            slots[slot].append(item)
        # 按 option_type 分组
        result = {}
        for slot, items in slots.items():
            groups = {}
            for item in items:
                ot = item["option_type"]
                if ot not in groups:
                    groups[ot] = {"option_type": ot, "items": [], "total_price": 0}
                groups[ot]["items"].append(item)
                groups[ot]["total_price"] += float(item["unit_price"] or 0) * item["quantity"]
            result[slot] = list(groups.values())
        return result
