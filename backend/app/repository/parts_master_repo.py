"""料号主表 Repository — l6.parts_master"""
import json
import re
from sqlalchemy import text
from app.models.base import l6_engine


class PartsMasterRepository:
    def __init__(self):
        self.engine = l6_engine

    def get(self, pn: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(text(
                "SELECT pn, name, category, section, unit_price, specs, tdp, cables_per, description "
                "FROM l6.parts_master WHERE pn=:pn"
            ), {"pn": pn}).mappings().first()
            if not row:
                return None
            d = dict(row)
            if isinstance(d.get("specs"), str):
                try:
                    d["specs"] = json.loads(d["specs"])
                except Exception:
                    d["specs"] = {}
            return d

    def list(self, category: str = None, search: str = None, section: str = None,
             specs_filters: dict = None) -> list:
        """specs_filters: 按 specs JSONB 内容过滤，键 → 值。
        数组字段（如 io_slot、chassis）传 list 做"包含"匹配（specs @> '{"io_slot":["IO3"]}'）；
        标量字段（如 option_type）传单值做等值匹配。键必须合法标识符（防注入）。"""
        with self.engine.connect() as c:
            sql = "SELECT pn, name, category, section, unit_price, specs, tdp, cables_per, description FROM l6.parts_master WHERE 1=1"
            params = {}
            if category:
                sql += " AND category=:cat"
                params["cat"] = category
            if section:
                sql += " AND section=:sec"
                params["sec"] = section
            if search:
                sql += " AND (pn ILIKE :s OR name ILIKE :s)"
                params["s"] = f"%{search}%"
            if specs_filters:
                for i, (k, v) in enumerate(specs_filters.items()):
                    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                        continue
                    sql += f" AND specs @> CAST(:sf{i} AS jsonb)"
                    params[f"sf{i}"] = json.dumps({k: v}, ensure_ascii=False)
            sql += " ORDER BY section, category, pn"
            rows = c.execute(text(sql), params).mappings().all()
            out = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("specs"), str):
                    try:
                        d["specs"] = json.loads(d["specs"])
                    except Exception:
                        d["specs"] = {}
                out.append(d)
            return out

    def categories(self) -> list:
        with self.engine.connect() as c:
            rows = c.execute(text(
                "SELECT DISTINCT category FROM l6.parts_master ORDER BY category"
            )).fetchall()
            return [r[0] for r in rows]

    def sections(self) -> list:
        """部段汇总：[{section, count, categories:[...]}]，按固定部段顺序。
        section 为空的归到 '(未分类)'。"""
        # 固定顺序，前端左栏主导航按此序展示
        order = ["基准件", "前面板件", "后面板件", "电源件"]
        with self.engine.connect() as c:
            rows = c.execute(text(
                "SELECT COALESCE(NULLIF(section,''),'(未分类)') AS s, category, COUNT(*) AS n "
                "FROM l6.parts_master GROUP BY s, category"
            )).fetchall()
        agg: dict[str, dict] = {}
        for sec, cat, n in rows:
            d = agg.setdefault(sec, {"section": sec, "count": 0, "categories": []})
            d["count"] += n
            d["categories"].append(cat)
        # 按 order 排序，未在 order 中的（如未分类）排末尾
        def _key(x):
            s = x["section"]
            return (order.index(s), s) if s in order else (len(order), s)
        out = sorted(agg.values(), key=_key)
        for d in out:
            d["categories"].sort()
        return out

    def upsert(self, data: dict) -> str:
        with self.engine.begin() as c:
            specs_json = json.dumps(data.get("specs")) if data.get("specs") else None
            c.execute(text("""
                INSERT INTO l6.parts_master (pn, name, category, section, unit_price, specs, tdp, cables_per, description)
                VALUES (:pn, :name, :category, :section, :unit_price, CAST(:specs AS jsonb), :tdp, :cables_per, :description)
                ON CONFLICT (pn) DO UPDATE SET
                    name=EXCLUDED.name, category=EXCLUDED.category, section=EXCLUDED.section,
                    unit_price=EXCLUDED.unit_price, specs=EXCLUDED.specs, tdp=EXCLUDED.tdp,
                    cables_per=EXCLUDED.cables_per, description=EXCLUDED.description
            """), {
                "pn": data["pn"], "name": data.get("name"), "category": data.get("category"),
                "section": data.get("section"), "unit_price": data.get("unit_price"),
                "specs": specs_json, "tdp": data.get("tdp"), "cables_per": data.get("cables_per"),
                "description": data.get("description"),
            })
        return data["pn"]

    def insert(self, data: dict) -> str:
        return self.upsert(data)

    # 可更新字段白名单：键 → SQL 列名（specs 需特殊处理）
    _UPDATABLE = ["name", "category", "section", "unit_price", "specs", "tdp", "cables_per", "description"]

    def update(self, pn: str, updates: dict) -> None:
        # 只更新 updates 中实际出现的白名单字段，未传字段保留原值
        present = [f for f in self._UPDATABLE if f in updates]
        if not present:
            return
        sets = []
        params: dict = {"pn": pn}
        for f in present:
            if f == "specs":
                v = updates.get("specs")
                sets.append("specs = CAST(:specs AS jsonb)")
                params["specs"] = json.dumps(v) if v is not None else None
            else:
                sets.append(f"{f} = :{f}")
                params[f] = updates.get(f)
        sql = f"UPDATE l6.parts_master SET {', '.join(sets)} WHERE pn = :pn"
        with self.engine.begin() as c:
            c.execute(text(sql), params)

    def delete(self, pn: str):
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM l6.parts_master WHERE pn=:pn"), {"pn": pn})
