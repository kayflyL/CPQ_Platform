"""后面板配置 Repository — 数据源已统一到 l6.parts_master.specs。

specs 承载后面板语义（见 backfill_rear_specs.py 回填约定）：
  - io_slot: string[]  能插的槽位（如 ["IO1","IO2","IO3"]）
  - option_type: string  槽内选项代号（x16/x8/nvme/sata/ocp_x8/ocp_x16）
  - chassis: string[]  适用机型系列（空/缺 = 全适用）

选项按 (io_slot × option_type) 分组派生：同组多颗料 = 一条捆绑选项（去黑盒，items 暴露明细）。
option.total_price = Σ member.unit_price（每件 1×）；数量由配置页步进器定，不再持久化。

旧表 l6_rear_panel_items 不再读取（仅 legacy 流程还用，见 [[l6-chassis-legacy-flow]]）。
"""
import json
from sqlalchemy import text
from app.models.base import l6_engine

# 槽内选项展示顺序（前端 OPTION_LABEL 对齐）
_OPTION_ORDER = {"x16": 0, "x8": 1, "nvme": 2, "sata": 3, "ocp_x8": 4, "ocp_x16": 5}


def _specs(row) -> dict:
    s = row.get("specs")
    if isinstance(s, str):
        try:
            return json.loads(s) or {}
        except Exception:
            return {}
    return s or {}


class RearIORepository:
    def __init__(self):
        self.engine = l6_engine

    def _raw_rear_parts(self) -> list:
        """所有承载后面板语义的料（specs.io_slot 为非空数组）。"""
        with self.engine.connect() as c:
            rows = c.execute(text(
                "SELECT pn, name, unit_price, specs FROM l6.parts_master "
                "WHERE specs ? 'io_slot' AND jsonb_array_length(COALESCE(specs->'io_slot','[]')) > 0 "
                "ORDER BY pn"
            )).mappings().all()
        return [
            {"pn": r["pn"], "name": r["name"], "unit_price": float(r["unit_price"] or 0),
             "specs": _specs(r)}
            for r in rows
        ]

    @staticmethod
    def _applies(specs: dict, series: str | None) -> bool:
        """无 chassis 约束 = 全适用；否则 chassis 数组需含 series。"""
        ch = specs.get("chassis")
        if not ch:
            return True
        if isinstance(ch, str):
            ch = [ch]
        return series is None or series in ch

    def list_options(self, series: str = None) -> list:
        """扁平列出适用某机型的后面板原料条目（分组前）。"""
        return [p for p in self._raw_rear_parts() if self._applies(p["specs"], series)]

    @staticmethod
    def _group(parts: list) -> dict:
        """按 io_slot → option_type 分组。option = {option_type, items, total_price}。"""
        slots: dict[str, dict] = {}
        for p in parts:
            sp = p["specs"]
            ioss = sp.get("io_slot") or []
            if isinstance(ioss, str):
                ioss = [ioss]
            ot = sp.get("option_type")
            if not ot:
                continue
            for slot in ioss:
                grp = slots.setdefault(slot, {}).setdefault(
                    ot, {"option_type": ot, "items": [], "total_price": 0.0})
                grp["items"].append({"pn": p["pn"], "name": p["name"],
                                     "unit_price": p["unit_price"]})
                grp["total_price"] = round(grp["total_price"] + p["unit_price"], 2)
        # 槽内选项按约定展示序排列
        for slot in slots:
            slots[slot] = dict(sorted(slots[slot].items(),
                                      key=lambda kv: _OPTION_ORDER.get(kv[0], 99)))
        return slots

    def get_slot_options(self, slot: str, series: str = None) -> list:
        parts = self.list_options(series)
        return list(self._group(parts).get(slot, {}).values())

    def get_all_slots(self, series: str = None) -> dict:
        parts = self.list_options(series)
        return {slot: list(ots.values()) for slot, ots in self._group(parts).items()}
