"""Repository for L6 BOM (Bill of Materials) templates and parts.

Manages STEP BY STEP configuration data for L6 machines that support
detailed component-level pricing.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class L6BomRepository:
    """Repository for L6 BOM templates and parts."""

    # ========== BOM Templates ==========

    def get_templates(self, l6_id: Optional[int] = None, step: Optional[int] = None) -> List[dict]:
        """Get BOM templates, optionally filtered by L6 ID and/or step."""
        q = "SELECT * FROM l6.l6_bom_templates WHERE 1=1"
        params = {}
        if l6_id is not None:
            q += " AND l6_id = :l6_id"
            params["l6_id"] = l6_id
        if step is not None:
            q += " AND step = :step"
            params["step"] = step
        q += " ORDER BY step, sort_order"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

    def get_template(self, template_id: int) -> Optional[dict]:
        """Get a single BOM template by ID."""
        q = "SELECT * FROM l6.l6_bom_templates WHERE template_id = :tid"
        with l6_engine.connect() as conn:
            row = conn.execute(text(q), {"tid": template_id}).mappings().first()
        return dict(row) if row else None

    def insert_template(self, data: dict) -> int:
        """Insert a new BOM template, return new template_id."""
        allowed = {"l6_id", "step", "template_name", "description", "base_price", "is_default", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_bom_templates ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_template(self, template_id: int, updates: dict) -> bool:
        """Update a BOM template."""
        allowed = {"step", "template_name", "description", "base_price", "is_default", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["tid"] = template_id
        q = f"UPDATE l6.l6_bom_templates SET {', '.join(fields)} WHERE template_id = :tid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_template(self, template_id: int) -> bool:
        """Delete a BOM template and all its parts."""
        # First delete all parts under this template
        q_parts = "DELETE FROM l6.l6_bom_parts WHERE template_id = :tid"
        q_template = "DELETE FROM l6.l6_bom_templates WHERE template_id = :tid"
        with l6_engine.begin() as conn:
            conn.execute(text(q_parts), {"tid": template_id})
            conn.execute(text(q_template), {"tid": template_id})
        return True

    # ========== BOM Parts ==========

    def get_parts(self, template_id: Optional[int] = None, step: Optional[int] = None) -> List[dict]:
        """Get BOM parts, optionally filtered by template_id and/or step."""
        q = "SELECT * FROM l6.l6_bom_parts WHERE 1=1"
        params = {}
        if template_id is not None:
            q += " AND template_id = :template_id"
            params["template_id"] = template_id
        if step is not None:
            q += " AND step = :step"
            params["step"] = step
        q += " ORDER BY sort_order"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

    def get_part(self, part_id: int) -> Optional[dict]:
        """Get a single BOM part by ID."""
        q = "SELECT * FROM l6.l6_bom_parts WHERE part_id = :pid"
        with l6_engine.connect() as conn:
            row = conn.execute(text(q), {"pid": part_id}).mappings().first()
        return dict(row) if row else None

    def insert_part(self, data: dict) -> int:
        """Insert a new BOM part, return new part_id."""
        allowed = {"template_id", "step", "pn", "part_name", "description", "unit_price", "quantity_default", "note", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_bom_parts ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_part(self, part_id: int, updates: dict) -> bool:
        """Update a BOM part."""
        allowed = {"step", "pn", "part_name", "description", "unit_price", "quantity_default", "note", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["pid"] = part_id
        q = f"UPDATE l6.l6_bom_parts SET {', '.join(fields)} WHERE part_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_part(self, part_id: int) -> bool:
        """Delete a BOM part."""
        q = "DELETE FROM l6.l6_bom_parts WHERE part_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"pid": part_id})
        return True

    # ========== Query Helpers ==========

    def get_template_with_parts(self, template_id: int) -> Optional[dict]:
        """Get a template with all its parts grouped by step."""
        template = self.get_template(template_id)
        if not template:
            return None
        parts = self.get_parts(template_id=template_id)
        # Group parts by step
        parts_by_step = {}
        for part in parts:
            step = part["step"]
            if step not in parts_by_step:
                parts_by_step[step] = []
            parts_by_step[step].append(part)
        template["parts_by_step"] = parts_by_step
        return template

    def get_l6_bom_summary(self, l6_id: int) -> dict:
        """Get BOM summary for an L6 machine (templates count, parts count)."""
        q_templates = "SELECT COUNT(*) FROM l6.l6_bom_templates WHERE l6_id = :l6_id"
        q_parts = """
            SELECT COUNT(*) FROM l6.l6_bom_parts 
            WHERE template_id IN (SELECT template_id FROM l6.l6_bom_templates WHERE l6_id = :l6_id)
        """
        with l6_engine.connect() as conn:
            templates_count = conn.execute(text(q_templates), {"l6_id": l6_id}).scalar() or 0
            parts_count = conn.execute(text(q_parts), {"l6_id": l6_id}).scalar() or 0
        return {"templates_count": templates_count, "parts_count": parts_count}

    def close(self):
        pass
