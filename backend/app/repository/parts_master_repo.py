"""料号主表 Repository — l6.parts_master + l6.part_taxonomy。
大类/STEP 是用户可增改的分类，定义在 l6.part_taxonomy（kind='major'/'step'）。"""
import json
import re
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models.base import l6_engine

# taxonomy kind → parts_master 列名（rename/delete 批量传播用）；label 给报错文案用
_TAXONOMY_COL = {"major": "major_category", "step": "section"}
_TAXONOMY_LABEL = {"major": "大类", "step": "STEP"}


class PartsMasterRepository:
    def __init__(self):
        self.engine = l6_engine

    def get(self, pn: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(text(
                "SELECT pn, name, category, major_category, section, unit_price, specs, tdp, cables_per, spec_text, description "
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
             major_category: str = None, specs_filters: dict = None) -> list:
        """specs_filters: 按 specs JSONB 内容过滤，键 → 值。
        数组字段（如 io_slot、chassis）传 list 做"包含"匹配（specs @> '{"io_slot":["IO3"]}'）；
        标量字段（如 option_type）传单值做等值匹配。键必须合法标识符（防注入）。"""
        with self.engine.connect() as c:
            sql = "SELECT pn, name, category, major_category, section, unit_price, specs, tdp, cables_per, spec_text, description FROM l6.parts_master WHERE 1=1"
            params = {}
            if category:
                sql += " AND category=:cat"
                params["cat"] = category
            if major_category:
                sql += " AND major_category=:mcat"
                params["mcat"] = major_category
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
            sql += " ORDER BY major_category, category, pn"
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

    def list_taxonomy(self, kind: str) -> list:
        """分类汇总（一级导航用）：读 part_taxonomy 有序列表 + parts_master 计数与子类。
        返回 [{name, count, categories:[子类...]}]。parts 中有但 taxonomy 没有的值作孤立项追加末尾。"""
        col = _TAXONOMY_COL.get(kind)
        if not col:
            raise ValueError(f"未知分类类型 {kind}，必须是 major / step")
        with self.engine.connect() as c:
            tax = [r[0] for r in c.execute(text(
                "SELECT name FROM l6.part_taxonomy WHERE kind=:k ORDER BY sort_order, name"
            ), {"k": kind}).fetchall()]
            rows = c.execute(text(
                f"SELECT COALESCE(NULLIF({col},''),'(未分类)') AS v, category, COUNT(*) AS n "
                f"FROM l6.parts_master GROUP BY v, category"
            )).fetchall()
        agg: dict[str, dict] = {}
        for v, cat, n in rows:
            d = agg.setdefault(v, {"name": v, "count": 0, "categories": []})
            d["count"] += n
            if cat:
                d["categories"].append(cat)
        out = [agg.pop(name, {"name": name, "count": 0, "categories": []}) for name in tax]
        out.extend(agg.values())  # 孤立项（parts 有、taxonomy 没有）
        for d in out:
            d["categories"].sort()
        return out

    def major_categories(self) -> list:
        """大类汇总（兼容旧端点）：[{major_category, count, categories}]，顺序由 part_taxonomy 决定。"""
        return [{"major_category": d["name"], "count": d["count"], "categories": d["categories"]}
                for d in self.list_taxonomy("major")]

    def sections(self) -> list:
        """STEP 部段汇总（兼容旧端点）：[{section, count, categories}]，顺序由 part_taxonomy 决定。"""
        return [{"section": d["name"], "count": d["count"], "categories": d["categories"]}
                for d in self.list_taxonomy("step")]

    # ---- 分类管理：增/改名/删，改名删除批量传播到 parts_master ----
    def add_taxonomy(self, kind: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("名称不能为空")
        if kind not in _TAXONOMY_COL:
            raise ValueError("分类类型必须是 major / step")
        with self.engine.begin() as c:
            next_order = c.execute(text(
                "SELECT COALESCE(MAX(sort_order),0)+1 FROM l6.part_taxonomy WHERE kind=:k"
            ), {"k": kind}).scalar()
            try:
                c.execute(text(
                    "INSERT INTO l6.part_taxonomy (kind, name, sort_order) VALUES (:k,:n,:s)"
                ), {"k": kind, "n": name, "s": next_order})
            except IntegrityError:
                raise ValueError(f"分类「{name}」已存在")
        return {"kind": kind, "name": name}

    def rename_taxonomy(self, kind: str, old_name: str, new_name: str) -> int:
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("新名称不能为空")
        col = _TAXONOMY_COL.get(kind)
        if not col:
            raise ValueError("分类类型必须是 major / step")
        if old_name == new_name:
            return 0
        with self.engine.begin() as c:
            if c.execute(text(
                "SELECT 1 FROM l6.part_taxonomy WHERE kind=:k AND name=:n"
            ), {"k": kind, "n": new_name}).first():
                raise ValueError(f"分类「{new_name}」已存在")
            updated = c.execute(text(
                f"UPDATE l6.parts_master SET {col}=:new WHERE {col}=:old"
            ), {"new": new_name, "old": old_name}).rowcount
            c.execute(text(
                "UPDATE l6.part_taxonomy SET name=:new, updated_at=now() WHERE kind=:k AND name=:old"
            ), {"new": new_name, "old": old_name, "k": kind})
        return updated

    def delete_taxonomy(self, kind: str, name: str) -> dict:
        name = (name or "").strip()
        col = _TAXONOMY_COL.get(kind)
        if not col:
            raise ValueError("分类类型必须是 major / step")
        with self.engine.begin() as c:
            in_use = c.execute(text(
                f"SELECT COUNT(*) FROM l6.parts_master WHERE {col}=:n"
            ), {"n": name}).scalar()
            if in_use:
                raise ValueError(f"{_TAXONOMY_LABEL[kind]}「{name}」被 {in_use} 个料号使用，请先把它们改到其它{_TAXONOMY_LABEL[kind]}再删除")
            c.execute(text(
                "DELETE FROM l6.part_taxonomy WHERE kind=:k AND name=:n"
            ), {"k": kind, "n": name})
        return {"name": name}

    def upsert(self, data: dict) -> str:
        with self.engine.begin() as c:
            specs_json = json.dumps(data.get("specs")) if data.get("specs") else None
            c.execute(text("""
                INSERT INTO l6.parts_master (pn, name, category, major_category, section, unit_price, specs, tdp, cables_per, spec_text, description)
                VALUES (:pn, :name, :category, :major_category, :section, :unit_price, CAST(:specs AS jsonb), :tdp, :cables_per, :spec_text, :description)
                ON CONFLICT (pn) DO UPDATE SET
                    name=EXCLUDED.name, category=EXCLUDED.category, major_category=EXCLUDED.major_category, section=EXCLUDED.section,
                    unit_price=EXCLUDED.unit_price, specs=EXCLUDED.specs, tdp=EXCLUDED.tdp,
                    cables_per=EXCLUDED.cables_per, spec_text=EXCLUDED.spec_text, description=EXCLUDED.description
            """), {
                "pn": data["pn"], "name": data.get("name"), "category": data.get("category"),
                "major_category": data.get("major_category"), "section": data.get("section"), "unit_price": data.get("unit_price"),
                "specs": specs_json, "tdp": data.get("tdp"), "cables_per": data.get("cables_per"),
                "spec_text": data.get("spec_text"), "description": data.get("description"),
            })
        return data["pn"]

    def insert(self, data: dict) -> str:
        """新建料号。若 PN 已存在则抛 ValueError。"""
        with self.engine.begin() as c:
            try:
                specs_json = json.dumps(data.get("specs")) if data.get("specs") else None
                c.execute(text("""
                    INSERT INTO l6.parts_master (pn, name, category, major_category, section, unit_price, specs, tdp, cables_per, spec_text, description)
                    VALUES (:pn, :name, :category, :major_category, :section, :unit_price, CAST(:specs AS jsonb), :tdp, :cables_per, :spec_text, :description)
                """), {
                    "pn": data["pn"], "name": data.get("name"), "category": data.get("category"),
                    "major_category": data.get("major_category"), "section": data.get("section"), "unit_price": data.get("unit_price"),
                    "specs": specs_json, "tdp": data.get("tdp"), "cables_per": data.get("cables_per"),
                    "spec_text": data.get("spec_text"), "description": data.get("description"),
                })
            except IntegrityError:
                raise ValueError(f"料号 {data['pn']} 已存在")
        return data["pn"]

    # 可更新字段白名单（specs 需转 JSONB）
    _UPDATABLE = ["pn", "name", "category", "major_category", "section", "unit_price", "specs", "tdp", "cables_per", "spec_text", "description"]

    def update(self, old_pn: str, updates: dict) -> None:
        """更新料号。old_pn 是原值（WHERE 条件），updates 包含新值。"""
        sets, params = [], {"_old_pn": old_pn}

        for f in self._UPDATABLE:
            if f not in updates:
                continue
            if f == "specs":
                sets.append("specs = CAST(:specs AS jsonb)")
                params["specs"] = json.dumps(updates["specs"]) if updates["specs"] else None
            else:
                sets.append(f"{f} = :{f}")
                params[f] = updates[f]

        if not sets:
            return

        sql = f"UPDATE l6.parts_master SET {', '.join(sets)} WHERE pn = :_old_pn"
        with self.engine.begin() as c:
            c.execute(text(sql), params)

    def delete(self, pn: str):
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM l6.parts_master WHERE pn=:pn"), {"pn": pn})

    def spec_keys(self) -> dict:
        """返回每个 category 下现有的 spec_key 列表（DISTINCT）。
        从 specs JSONB 字段提取所有键，按 category 分组。"""
        with self.engine.connect() as c:
            # 先获取所有料的 category 和 specs
            rows = c.execute(text(
                "SELECT category, specs FROM l6.parts_master WHERE category IS NOT NULL AND specs IS NOT NULL"
            )).fetchall()

        result: dict[str, set] = {}
        for category, specs_json in rows:
            if not category:
                continue
            if isinstance(specs_json, str):
                try:
                    specs = json.loads(specs_json)
                except:
                    continue
            elif isinstance(specs_json, dict):
                specs = specs_json
            else:
                continue

            if not isinstance(specs, dict):
                continue

            # 收集该 category 下的所有 spec_key
            if category not in result:
                result[category] = set()
            for key in specs.keys():
                result[category].add(key)

        # 转 set 为 sorted list
        return {cat: sorted(keys) for cat, keys in sorted(result.items())}

    def spec_values(self, category: str, spec_key: str) -> list:
        """返回指定 category + spec_key 下的所有不同值（DISTINCT）。"""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", spec_key):
            return []

        with self.engine.connect() as c:
            # 使用 jsonb_extract_path_text 提取值
            rows = c.execute(text("""
                SELECT DISTINCT jsonb_extract_path_text(specs, :key) AS val
                FROM l6.parts_master
                WHERE category = :cat AND specs ? :key
                ORDER BY val
            """), {"cat": category, "key": spec_key}).fetchall()

        # 过滤掉 None/空字符串，返回值列表
        return [r[0] for r in rows if r[0] and str(r[0]).strip()]
