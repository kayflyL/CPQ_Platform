"""Repository for L6 whole-machine price records.

Uses raw SQL because l6_data.db:l6_records has NO declared primary key —
just (chassis, model, motherboard, backplane, gpu_expansion, psu, drive_bays, rail_kit, power_cord, price, update_date, note).
"""
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import text
from app.models.base import l6_engine, l6_history_engine


class L6Repository:

    def get_all_records(self, search: str = "",
                        page: int = 1, page_size: int = 50) -> Tuple[List[dict], int]:
        base = "SELECT id, * FROM l6.l6_records"
        params: dict = {}
        conditions = []
        if search:
            conditions.append("(model LIKE :s OR motherboard LIKE :s)")
            params["s"] = f"%{search}%"
        if conditions:
            base += " WHERE " + " AND ".join(conditions)
        base += " ORDER BY sort_order ASC, update_date DESC"

        # Count
        count_sql = "SELECT COUNT(*) FROM l6.l6_records"
        if conditions:
            count_sql += " WHERE " + " AND ".join(conditions)
        with l6_engine.connect() as conn:
            total = conn.execute(text(count_sql), params).scalar() or 0

        # Paginated
        base += " LIMIT :lim OFFSET :off"
        params["lim"] = page_size
        params["off"] = (page - 1) * page_size
        with l6_engine.connect() as conn:
            rows = conn.execute(text(base), params).mappings().all()
        return [dict(r) for r in rows], total

    def update_record(self, record_id: int, updates: dict) -> bool:
        fields = []
        values: dict = {}
        for key, val in updates.items():
            if key in ("chassis", "model", "motherboard", "backplane",
                       "gpu_expansion", "psu", "drive_bays", "rail_kit",
                       "power_cord", "price", "note"):
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        fields.append("update_date = :ud")
        values["ud"] = datetime.now().strftime("%Y-%m-%d")
        values["rid"] = record_id
        q = f"UPDATE l6.l6_records SET {', '.join(fields)} WHERE id = :rid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    # Whitelist of columns allowed in INSERT/UPDATE (defense against SQL injection via column names)
    _ALLOWED_COLS = {
        "chassis", "model", "motherboard", "backplane", "gpu_expansion",
        "psu", "drive_bays", "rail_kit", "power_cord", "price", "note",
        "sort_order",
    }

    def insert_record(self, data: dict) -> int:
        """插入L6记录，返回新记录的id"""
        # Filter to whitelisted columns only (prevent SQL injection via column names)
        safe_data = {k: v for k, v in data.items() if k in self._ALLOWED_COLS}
        if not safe_data:
            return 0
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_records ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def get_grouped_by_model(self, search: str = "") -> List[dict]:
        """按机型(model)聚合所有L6记录，返回分组数据"""
        base = "SELECT id, * FROM l6.l6_records"
        params: dict = {}
        conditions = []
        if search:
            conditions.append("(model LIKE :s OR motherboard LIKE :s OR chassis LIKE :s)")
            params["s"] = f"%{search}%"
        if conditions:
            base += " WHERE " + " AND ".join(conditions)
        base += " ORDER BY model, update_date DESC"

        with l6_engine.connect() as conn:
            rows = conn.execute(text(base), params).mappings().all()

        # 按 model 分组
        groups: dict = {}
        for row in rows:
            model = row["model"] or "(未命名机型)"
            if model not in groups:
                groups[model] = {
                    "model": model,
                    "records": [],
                    "price_min": float("inf"),
                    "price_max": float("-inf"),
                    "count": 0
                }
            record = dict(row)
            price = record.get("price") or 0
            groups[model]["records"].append(record)
            groups[model]["count"] += 1
            if price < groups[model]["price_min"]:
                groups[model]["price_min"] = price
            if price > groups[model]["price_max"]:
                groups[model]["price_max"] = price

        # 转换 inf/-inf 为 0
        result = []
        for g in groups.values():
            if g["price_min"] == float("inf"):
                g["price_min"] = 0
            if g["price_max"] == float("-inf"):
                g["price_max"] = 0
            result.append(g)

        return result

    def update_sort_order(self, record_id: int, sort_order: int) -> bool:
        """更新单条记录的排序值"""
        q = "UPDATE l6.l6_records SET sort_order = :sort_order WHERE id = :rid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"sort_order": sort_order, "rid": record_id})
        return True

    def batch_update_sort_order(self, items: List[dict]) -> bool:
        """批量更新排序（每个 item 需要 id 和 sort_order）"""
        q = "UPDATE l6.l6_records SET sort_order = :sort_order WHERE id = :rid"
        with l6_engine.begin() as conn:
            for item in items:
                conn.execute(text(q), {
                    "sort_order": item.get("sort_order", 0),
                    "rid": item.get("id")
                })
        return True

    def delete_record(self, record_id: int) -> bool:
        """删除单条L6记录"""
        q = "DELETE FROM l6.l6_records WHERE id = :rid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"rid": record_id})
        return True

    def get_history(self, record_id: int, limit: int = 50) -> List[dict]:
        """获取指定L6记录的价格历史"""
        q = """
            SELECT id, l6_record_id as record_id, price, note, created_at
            FROM l6_history.l6_price_history
            WHERE l6_record_id = :rid
            ORDER BY created_at DESC
            LIMIT :lim
        """
        with l6_history_engine.connect() as conn:
            rows = conn.execute(text(q), {"rid": record_id, "lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    def save_history_snapshot(self, record_id: int, price: float, note: str = "") -> bool:
        """保存L6记录的价格快照到历史表"""
        q = """
            INSERT INTO l6_history.l6_price_history (l6_record_id, price, note, created_at)
            VALUES (:rid, :price, :note, :ts)
        """
        with l6_history_engine.begin() as conn:
            conn.execute(text(q), {
                "rid": record_id,
                "price": price,
                "note": note,
                "ts": datetime.now().isoformat()
            })
        return True

    def close(self):
        pass  # Engine is shared
