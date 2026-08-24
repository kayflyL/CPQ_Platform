"""base_configs + base_config_parts repo — 基准配置（引用 parts_master）。

对应管理面「基准配置组装」。底盘件清单 JOIN parts_master 取 name/price/specs。
原生 SQL，走 l6_engine。
"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


def _json(v):
    """JSONB 列读归一化（psycopg2 对 jsonb 一般直接返回 dict/list，历史/异常时可能为 str）。"""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


class BaseConfigRepository:
    def list(self, series: Optional[str] = None, form: Optional[str] = None,
             bays: Optional[int] = None, server_type_id: Optional[int] = None,
             model_id: Optional[int] = None, unassigned: bool = False) -> List[dict]:
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
        if model_id is not None:
            q += " AND model_id=:mid"; p["mid"] = model_id
        if unassigned:
            q += " AND model_id IS NULL"
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
            # config_content / psu_wattages JSONB 读归一化（psycopg2 可能返回 str）
            cc = cfg.get("config_content")
            if isinstance(cc, str):
                try:
                    cfg["config_content"] = json.loads(cc)
                except Exception:
                    cfg["config_content"] = None
            pw = cfg.get("psu_wattages")
            if isinstance(pw, str):
                try:
                    cfg["psu_wattages"] = json.loads(pw)
                except Exception:
                    cfg["psu_wattages"] = None
        return configs

    def list_forms(self) -> list:
        """DISTINCT form（数据驱动，贴需求分析词表「动态下拉」诉求）。"""
        with l6_engine.connect() as c:
            rows = c.execute(text(
                "SELECT DISTINCT form FROM l6.base_configs "
                "WHERE form IS NOT NULL AND form <> '' ORDER BY form"
            )).fetchall()
        return [r[0] for r in rows]

    def cost_analysis(self) -> List[dict]:
        """全量基准配置的裸机成本分析（编辑器右侧「机型成本对比」卡数据源，与前端面板同口径）：
        底盘件 + 后面板默认卡(每槽1套，PN 与底盘件去重防双计) + 前面板默认线缆(每盘类1根)
        + 默认 PSU×psu_bays(满配预估)。缺价件(unit_price NULL / PN 库外)不计入、只计数。
        价格源 = parts_master.unit_price 实时查询；裸机口径，KP 配置件(CPU/内存/盘体/GPU/网卡)不在内。"""
        with l6_engine.connect() as c:
            cfgs = [dict(r) for r in c.execute(text(
                "SELECT b.id, b.name, b.series, b.form, b.model_id, b.psu_bays,"
                " b.rear_slots, b.config_content, m.name AS model_name"
                " FROM l6.base_configs b LEFT JOIN l6.server_models m ON b.model_id = m.id"
                " ORDER BY b.sort_order, b.id"
            )).mappings().all()]
            part_rows = c.execute(text(
                "SELECT p.config_id, p.pn, p.quantity, m.unit_price"
                " FROM l6.base_config_parts p LEFT JOIN l6.parts_master m ON p.pn = m.pn"
            )).mappings().all()

        prices: dict = {}
        chassis: dict = {}
        for r in part_rows:
            prices[r["pn"]] = r["unit_price"]
            d = chassis.setdefault(r["config_id"], {"total": 0.0, "missing": 0, "pns": set()})
            d["pns"].add(r["pn"])
            if r["unit_price"] is None:
                d["missing"] += 1
            else:
                d["total"] += float(r["unit_price"]) * int(r["quantity"] or 0)

        # 引用件价格补查（后面板默认/线缆/PSU 的 PN 通常不在 base_config_parts）
        extra = set()
        for cfg in cfgs:
            cc = _json(cfg.get("config_content"))
            cc = cc if isinstance(cc, dict) else {}
            slots = _json(cfg.get("rear_slots"))
            if isinstance(slots, list):
                for s in slots:
                    if isinstance(s, dict):
                        extra.update(pn for pn in (s.get("defaults") or []) if pn)
            fc = cc.get("front_cables")
            if isinstance(fc, dict):
                extra.update(pn for pn in fc.values() if pn)
            if cc.get("default_psu_pn"):
                extra.add(cc["default_psu_pn"])
        extra -= set(prices)
        if extra:
            with l6_engine.connect() as c:
                for r in c.execute(text(
                    "SELECT pn, unit_price FROM l6.parts_master WHERE pn = ANY(:pns)"
                ), {"pns": list(extra)}).mappings().all():
                    prices[r["pn"]] = r["unit_price"]

        out = []
        for cfg in cfgs:
            ch = chassis.get(cfg["id"]) or {"total": 0.0, "missing": 0, "pns": set()}
            seen: set = set(ch["pns"])
            missing = ch["missing"]
            rear = cables = psu = 0.0

            def _cost(pn) -> float:
                nonlocal missing
                up = prices.get(pn)
                if up is None:
                    missing += 1
                    return 0.0
                return float(up)

            slots = _json(cfg.get("rear_slots"))
            if isinstance(slots, list):
                for s in slots:
                    if not isinstance(s, dict):
                        continue
                    for pn in (s.get("defaults") or []):
                        if not pn or pn in seen:
                            continue
                        seen.add(pn)
                        rear += _cost(pn)
            cc = _json(cfg.get("config_content"))
            cc = cc if isinstance(cc, dict) else {}
            fc = cc.get("front_cables")
            if isinstance(fc, dict):
                for pn in fc.values():
                    if not pn or pn in seen:
                        continue
                    seen.add(pn)
                    cables += _cost(pn)
            if cc.get("default_psu_pn") and cc["default_psu_pn"] not in seen:
                psu += _cost(cc["default_psu_pn"]) * int(cfg.get("psu_bays") or 0)

            out.append({
                "id": cfg["id"], "name": cfg["name"], "series": cfg.get("series") or "",
                "form": cfg.get("form") or "", "model_id": cfg.get("model_id"),
                "model_name": cfg.get("model_name"),
                "total": round(ch["total"] + rear + cables + psu, 2),
                "by_source": {"chassis": round(ch["total"], 2), "rear": round(rear, 2),
                              "cables": round(cables, 2), "psu": round(psu, 2)},
                "missing": missing,
            })
        return out

    def get(self, config_id: int) -> Optional[dict]:
        with l6_engine.connect() as c:
            r = c.execute(text("SELECT * FROM l6.base_configs WHERE id=:id"),
                          {"id": config_id}).mappings().first()
        if not r:
            return None
        d = dict(r)
        cc = d.get("config_content")
        if isinstance(cc, str):
            try:
                d["config_content"] = json.loads(cc)
            except Exception:
                d["config_content"] = None
        pw = d.get("psu_wattages")
        if isinstance(pw, str):
            try:
                d["psu_wattages"] = json.loads(pw)
            except Exception:
                d["psu_wattages"] = None
        return d

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
                   "bp_tri_pn", "bp_dc_pn", "gpu_arch_default", "sort_order", "bom_template_id",
                   "psu_bays", "rear_slots", "gpu_slots", "max_tdp",
                   "psu_wattages", "max_cpu", "max_dimm", "mem_channels",
                   "model_id", "config_content"}
        d = {k: v for k, v in data.items() if k in allowed}
        if "name" not in d:
            raise ValueError("name required")
        if isinstance(d.get("rear_slots"), (list, dict)):
            d["rear_slots"] = json.dumps(d["rear_slots"], ensure_ascii=False)
        if isinstance(d.get("psu_wattages"), (list, dict)):
            d["psu_wattages"] = json.dumps(d["psu_wattages"], ensure_ascii=False)
        if isinstance(d.get("config_content"), (dict, list)):
            d["config_content"] = json.dumps(d["config_content"], ensure_ascii=False)
        cols = list(d.keys())
        val_list = ",".join(f"CAST(:{k} AS jsonb)" if k == "config_content" else f":{k}" for k in cols)
        q = f"INSERT INTO l6.base_configs ({','.join(cols)}) VALUES ({val_list}) RETURNING id"
        with l6_engine.begin() as c:
            return c.execute(text(q), d).scalar()

    def update(self, config_id: int, updates: dict) -> bool:
        allowed = {"name", "server_type_id", "series", "model", "form", "bays",
                   "bp_tri_pn", "bp_dc_pn", "gpu_arch_default", "sort_order", "bom_template_id",
                   "psu_bays", "rear_slots", "gpu_slots", "max_tdp",
                   "psu_wattages", "max_cpu", "max_dimm", "mem_channels",
                   "model_id", "config_content"}
        f, v = [], {}
        for k, val in updates.items():
            if k not in allowed:
                continue
            if k == "config_content" and isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
                f.append("config_content = CAST(:config_content AS jsonb)")
            elif k == "psu_wattages" and isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
                f.append("psu_wattages = CAST(:psu_wattages AS jsonb)")
            else:
                f.append(f"{k}=:{k}")
            v[k] = val
        if isinstance(v.get("rear_slots"), (list, dict)):
            v["rear_slots"] = json.dumps(v["rear_slots"], ensure_ascii=False)
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
