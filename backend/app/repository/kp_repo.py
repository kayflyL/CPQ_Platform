"""Repository for KP (Key Parts) price records.

Uses raw SQL (text()) because kp_data.db:kp_records has NO declared primary key —
just (category, model, price, currency, date, note). ORM mapping is unreliable here.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import text
from app.models.base import kp_engine


class KPRepository:
    """Thin wrapper over kp_data.db using raw SQL for reliability."""

    def get_latest_prices(self, search: str = "", category: str = "", sort_by: str = "date", sort_order: str = "desc") -> List[dict]:
        # Whitelist sortable fields to prevent SQL injection
        allowed_sort = {"model", "price", "date", "record_count", "category"}
        if sort_by not in allowed_sort:
            sort_by = "date"
        if sort_order.lower() not in ("asc", "desc"):
            sort_order = "desc"
        
        base_q = """
            SELECT rowid as id, category, model, price, currency, date, note,
                   (SELECT COUNT(*) FROM kp_records WHERE model = sub.model) as record_count
            FROM (
                SELECT rowid, category, model, price, currency, date, note,
                       ROW_NUMBER() OVER (PARTITION BY model ORDER BY date DESC) as rn
                FROM kp_records
            ) sub
            WHERE rn = 1
        """
        params: dict = {}
        conditions = []
        if search:
            conditions.append("(model LIKE :s OR category LIKE :s OR note LIKE :s)")
            params["s"] = f"%{search}%"
        if category:
            conditions.append("category = :cat")
            params["cat"] = category
        if conditions:
            base_q += " AND " + " AND ".join(conditions)
        base_q += f" ORDER BY {sort_by} {sort_order.upper()}"

        with kp_engine.connect() as conn:
            rows = conn.execute(text(base_q), params).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_price_for_model(self, model: str) -> Optional[dict]:
        q = """
            SELECT category, model, price, currency, date, note
            FROM kp_records
            WHERE model = :m
            ORDER BY date DESC
            LIMIT 1
        """
        with kp_engine.connect() as conn:
            row = conn.execute(text(q), {"m": model}).mappings().first()
        return dict(row) if row else None

    def fuzzy_match_price(self, model_fragment: str) -> Optional[dict]:
        q = """
            SELECT category, model, price, currency, date, note
            FROM kp_records
            WHERE model LIKE :f
            ORDER BY date DESC
            LIMIT 1
        """
        with kp_engine.connect() as conn:
            row = conn.execute(text(q), {"f": f"%{model_fragment}%"}).mappings().first()
        return dict(row) if row else None

    def get_price_history(self, model: str, limit: int = 20) -> List[dict]:
        q = """
            SELECT rowid as id, category, model, price, currency, date, note
            FROM kp_records
            WHERE model = :m
            ORDER BY date DESC
            LIMIT :l
        """
        with kp_engine.connect() as conn:
            rows = conn.execute(text(q), {"m": model, "l": limit}).mappings().all()
        return [dict(r) for r in rows]

    def insert_price(self, category: str, model: str, price: float,
                     currency: str = "RMB", date: str = None, note: str = "") -> bool:
        q = """
            INSERT INTO kp_records (category, model, price, currency, date, note)
            VALUES (:c, :m, :p, :cu, :d, :n)
        """
        with kp_engine.begin() as conn:
            conn.execute(text(q), {
                "c": category, "m": model, "p": price,
                "cu": currency, "d": date or datetime.now().strftime("%Y-%m-%d"),
                "n": note,
            })
        return True

    def get_categories(self) -> List[dict]:
        """Return all unique categories with their model counts."""
        q = """
            SELECT category, COUNT(DISTINCT model) as count
            FROM kp_records
            GROUP BY category
            ORDER BY count DESC
        """
        with kp_engine.connect() as conn:
            rows = conn.execute(text(q)).mappings().all()
        return [dict(r) for r in rows]

    def get_by_category(self, category: str, search: str = "") -> List[dict]:
        """Get latest price for each model in a given category, with record count."""
        base_q = """
            SELECT rowid as id, category, model, price, currency, date, note,
                   (SELECT COUNT(*) FROM kp_records WHERE model = sub.model) as record_count
            FROM (
                SELECT rowid, category, model, price, currency, date, note,
                       ROW_NUMBER() OVER (PARTITION BY model ORDER BY date DESC) as rn
                FROM kp_records
                WHERE category = :cat
            ) sub
            WHERE rn = 1
        """
        params: dict = {"cat": category}
        if search:
            base_q += " AND (model LIKE :s OR note LIKE :s)"
            params["s"] = f"%{search}%"
        base_q += " ORDER BY model"

        with kp_engine.connect() as conn:
            rows = conn.execute(text(base_q), params).mappings().all()
        return [dict(r) for r in rows]

    def rename_model(self, old_model: str, new_model: str) -> bool:
        """Rename a model across all its history records."""
        q = "UPDATE kp_records SET model = :new WHERE model = :old"
        with kp_engine.begin() as conn:
            conn.execute(text(q), {"new": new_model, "old": old_model})
        return True

    def update_note(self, model: str, note: str) -> bool:
        """Update note on the latest record for a model (insert a note-only record)."""
        # Get latest record's category and price to create a note-update record
        latest = self.get_latest_price_for_model(model)
        if not latest:
            return False
        self.insert_price(
            category=latest["category"],
            model=model,
            price=latest["price"],
            currency=latest.get("currency", "RMB"),
            note=note
        )
        return True

    def get_distinct_cpu_models(self) -> List[str]:
        """获取所有去重的CPU型号（从kp_records中category='CPU'）"""
        q = """
            SELECT DISTINCT model
            FROM kp_records
            WHERE category = 'CPU'
              AND model IS NOT NULL
              AND model != ''
            ORDER BY model
        """
        with kp_engine.connect() as conn:
            rows = conn.execute(text(q)).fetchall()
        return [r[0] for r in rows]

    def close(self):
        pass  # Engine is shared; no per-repo session to close
