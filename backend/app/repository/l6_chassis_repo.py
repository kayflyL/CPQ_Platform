"""Repository for L6 机箱库 — 4个数据库的CRUD操作"""
import json
from typing import List, Optional
from sqlalchemy import text
from app.models.base import l6_engine


class L6ChassisRepository:
    """Repository for L6 chassis libraries (4 databases)"""

    # ========== 基准配置库 ==========

    def get_base_configs(
        self,
        chassis: Optional[str] = None,
        chassis_series: Optional[str] = None,
        drive_bays: Optional[str] = None,
        backplane_type: Optional[str] = None,
    ) -> List[dict]:
        """获取基准配置列表，支持多维度筛选"""
        q = "SELECT * FROM l6.l6_base_configs_old WHERE 1=1"
        params = {}
        if chassis:
            q += " AND chassis = :chassis"
            params["chassis"] = chassis
        if chassis_series:
            q += " AND chassis_series = :chassis_series"
            params["chassis_series"] = chassis_series
        if drive_bays:
            q += " AND drive_bays = :drive_bays"
            params["drive_bays"] = drive_bays
        if backplane_type:
            q += " AND backplane_type = :backplane_type"
            params["backplane_type"] = backplane_type
        q += " ORDER BY sort_order, config_id"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("base_price") is not None:
                d["base_price"] = float(d["base_price"])
            out.append(d)
        return out

    def get_distinct_values(self) -> dict:
        """获取所有基准配置的各维度去重值（用于前端级联筛选）"""
        with l6_engine.connect() as conn:
            chassis_list = [r[0] for r in conn.execute(
                text("SELECT DISTINCT chassis FROM l6.l6_base_configs_old WHERE chassis IS NOT NULL AND chassis != '' ORDER BY chassis")
            ).all()]
            series = [r[0] for r in conn.execute(
                text("SELECT DISTINCT chassis_series FROM l6.l6_base_configs_old WHERE chassis_series IS NOT NULL AND chassis_series != '' ORDER BY chassis_series")
            ).all()]
            bays = [r[0] for r in conn.execute(
                text("SELECT DISTINCT drive_bays FROM l6.l6_base_configs_old WHERE drive_bays IS NOT NULL AND drive_bays != '' ORDER BY drive_bays")
            ).all()]
            backplanes = [r[0] for r in conn.execute(
                text("SELECT DISTINCT backplane_type FROM l6.l6_base_configs_old WHERE backplane_type IS NOT NULL AND backplane_type != '' ORDER BY backplane_type")
            ).all()]
        return {
            "chassis": chassis_list,
            "chassis_series": series,
            "drive_bays": bays,
            "backplane_type": backplanes,
        }

    def get_base_config(self, config_id: int) -> Optional[dict]:
        """获取单个基准配置"""
        q = "SELECT * FROM l6.l6_base_configs_old WHERE config_id = :cid"
        with l6_engine.connect() as conn:
            row = conn.execute(text(q), {"cid": config_id}).mappings().first()
        if not row:
            return None
        d = dict(row)
        if d.get("base_price") is not None:
            d["base_price"] = float(d["base_price"])
        return d

    def get_base_config_with_parts(self, config_id: int) -> Optional[dict]:
        """获取基准配置及其组件清单"""
        config = self.get_base_config(config_id)
        if not config:
            return None
        parts = self.get_base_config_parts(config_id)
        config["parts"] = parts
        return config

    def insert_base_config(self, data: dict) -> int:
        """新增基准配置"""
        allowed = {"chassis", "chassis_series", "description", "excludes", "base_price", "sort_order", "drive_bays", "backplane_type"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_base_configs_old ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_base_config(self, config_id: int, updates: dict) -> bool:
        """更新基准配置"""
        allowed = {"chassis", "chassis_series", "description", "excludes", "base_price", "sort_order", "drive_bays", "backplane_type"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["cid"] = config_id
        q = f"UPDATE l6.l6_base_configs_old SET {', '.join(fields)} WHERE config_id = :cid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_base_config(self, config_id: int) -> bool:
        """删除基准配置及其组件"""
        q_parts = "DELETE FROM l6.l6_base_config_parts_old WHERE config_id = :cid"
        q_config = "DELETE FROM l6.l6_base_configs_old WHERE config_id = :cid"
        with l6_engine.begin() as conn:
            conn.execute(text(q_parts), {"cid": config_id})
            conn.execute(text(q_config), {"cid": config_id})
        return True

    # ========== 基准配置组件 ==========

    def get_base_config_parts(self, config_id: int) -> List[dict]:
        """获取基准配置的组件清单"""
        q = "SELECT * FROM l6.l6_base_config_parts_old WHERE config_id = :cid ORDER BY sort_order"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), {"cid": config_id}).mappings().all()
        return [dict(r) for r in rows]

    def insert_base_config_part(self, data: dict) -> int:
        """新增组件"""
        allowed = {"config_id", "pn", "part_name", "description", "unit_price", "quantity", "note", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_base_config_parts_old ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_base_config_part(self, part_id: int, updates: dict) -> bool:
        """更新组件"""
        allowed = {"pn", "part_name", "description", "unit_price", "quantity", "note", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["pid"] = part_id
        q = f"UPDATE l6.l6_base_config_parts_old SET {', '.join(fields)} WHERE part_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_base_config_part(self, part_id: int) -> bool:
        """删除组件"""
        q = "DELETE FROM l6.l6_base_config_parts_old WHERE part_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"pid": part_id})
        return True

    # ========== 前面板线缆库 ==========

    def get_front_panel_items(
        self,
        drive_bays: Optional[str] = None,
        backplane_type: Optional[str] = None,
    ) -> List[dict]:
        """前面板线缆 — 统一数据源，从 parts_master 读取（category='前面板线缆'）。
        原 l6_front_panel_items 表已废弃，前端字段经 specs 映射兼容返回。"""
        from app.repository.parts_master_repo import PartsMasterRepository
        rows = PartsMasterRepository().list(category="前面板线缆")
        results = []
        for r in rows:
            specs = r.get("specs") or {}
            bays = specs.get("drive_bays") or []
            backs = specs.get("backplane") or []
            if drive_bays and bays and drive_bays not in bays:
                continue
            if backplane_type and backs and backplane_type not in backs:
                continue
            results.append({
                "item_id": r.get("pn"),
                "pn": r.get("pn"),
                "cable_type": specs.get("kind") or r.get("sub_type") or "",
                "part_name": r.get("name") or "",
                "description": specs.get("description") or "",
                "unit_price": float(r.get("unit_price") or 0),
                "group_size": specs.get("group_size") or 1,
                "applicable_drive_bays": bays,
                "applicable_backplane": backs,
            })
        return results

    # ---- front_panel CRUD 已废弃：数据源统一到 parts_master(category='前面板线缆')。
    # 原 l6_front_panel_items 表已移除；前端 useL6ChassisConfig 只读（get_front_panel_items），不调以下方法。
    # 如需重新启用管理面，应改写为 PartsMasterRepository 委托。
    def insert_front_panel_item(self, data: dict) -> int:
        """新增前面板线缆"""
        allowed = {"cable_type", "pn", "part_name", "description", "unit_price", "group_size", "applicable_chassis", "applicable_drive_bays", "applicable_backplane", "note", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        # JSON 字段序列化
        for json_field in ("applicable_chassis", "applicable_drive_bays", "applicable_backplane"):
            if json_field in safe_data and isinstance(safe_data[json_field], list):
                safe_data[json_field] = json.dumps(safe_data[json_field])
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_front_panel_items ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_front_panel_item(self, item_id: int, updates: dict) -> bool:
        """更新前面板线缆"""
        allowed = {"cable_type", "pn", "part_name", "description", "unit_price", "group_size", "applicable_chassis", "applicable_drive_bays", "applicable_backplane", "note", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                if key in ("applicable_chassis", "applicable_drive_bays", "applicable_backplane") and isinstance(val, list):
                    val = json.dumps(val)
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["iid"] = item_id
        q = f"UPDATE l6.l6_front_panel_items SET {', '.join(fields)} WHERE item_id = :iid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_front_panel_item(self, item_id: int) -> bool:
        """删除前面板线缆"""
        q = "DELETE FROM l6.l6_front_panel_items WHERE item_id = :iid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"iid": item_id})
        return True

    # ========== 后面板硬盘库 ==========

    def get_rear_panel_items(
        self,
        chassis: Optional[str] = None,
        backplane_type: Optional[str] = None,
    ) -> List[dict]:
        """获取后面板选项列表，按属性维度过滤"""
        q = "SELECT * FROM l6.l6_rear_panel_items WHERE 1=1"
        params = {}
        q += " ORDER BY sort_order, item_id"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        results = []
        for r in rows:
            item = dict(r)
            # 按 chassis 过滤
            if chassis and item.get("applicable_chassis"):
                try:
                    chassis_list = json.loads(item["applicable_chassis"])
                    if chassis_list and chassis not in chassis_list:
                        continue
                except:
                    pass
            # 按 backplane_type 过滤
            if backplane_type and item.get("applicable_backplane"):
                try:
                    types = json.loads(item["applicable_backplane"])
                    if types and backplane_type not in types:
                        continue
                except:
                    pass
            results.append(item)
        return results

    def insert_rear_panel_item(self, data: dict) -> int:
        """新增后面板选项"""
        allowed = {"io_slot", "option_type", "pn", "part_name", "description", "unit_price", "quantity", "applicable_chassis", "applicable_backplane", "note", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        # JSON 字段序列化
        for json_field in ("applicable_chassis", "applicable_backplane"):
            if json_field in safe_data and isinstance(safe_data[json_field], list):
                safe_data[json_field] = json.dumps(safe_data[json_field])
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_rear_panel_items ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_rear_panel_item(self, item_id: int, updates: dict) -> bool:
        """更新后面板选项"""
        allowed = {"io_slot", "option_type", "pn", "part_name", "description", "unit_price", "quantity", "applicable_chassis", "applicable_backplane", "note", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                if key in ("applicable_chassis", "applicable_backplane") and isinstance(val, list):
                    val = json.dumps(val)
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["iid"] = item_id
        q = f"UPDATE l6.l6_rear_panel_items SET {', '.join(fields)} WHERE item_id = :iid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_rear_panel_item(self, item_id: int) -> bool:
        """删除后面板选项"""
        q = "DELETE FROM l6.l6_rear_panel_items WHERE item_id = :iid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"iid": item_id})
        return True

    # ========== 电源库 ==========

    def get_psu_options(self, chassis_type: Optional[str] = None) -> List[dict]:
        """获取PSU选项列表，可按机箱类型过滤"""
        q = "SELECT * FROM l6.l6_psu_options WHERE 1=1"
        params = {}
        if chassis_type:
            q += " AND (applicable_chassis LIKE :pattern OR applicable_chassis IS NULL OR applicable_chassis = '[]')"
            params["pattern"] = f'%{chassis_type}%'
        q += " ORDER BY sort_order, psu_id"
        with l6_engine.connect() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        results = []
        for r in rows:
            item = dict(r)
            if chassis_type and item.get("applicable_chassis"):
                try:
                    chassis_list = json.loads(item["applicable_chassis"])
                    if chassis_type not in chassis_list:
                        continue
                except:
                    pass
            results.append(item)
        return results

    def insert_psu_option(self, data: dict) -> int:
        """新增PSU选项"""
        allowed = {"wattage", "pn", "part_name", "description", "unit_price", "applicable_chassis", "note", "sort_order"}
        safe_data = {k: v for k, v in data.items() if k in allowed}
        if not safe_data:
            return 0
        if "applicable_chassis" in safe_data and isinstance(safe_data["applicable_chassis"], list):
            safe_data["applicable_chassis"] = json.dumps(safe_data["applicable_chassis"])
        cols = list(safe_data.keys())
        placeholders = ", ".join([f":{k}" for k in cols])
        columns = ", ".join(cols)
        q = f"INSERT INTO l6.l6_psu_options ({columns}) VALUES ({placeholders})"
        with l6_engine.begin() as conn:
            result = conn.execute(text(q), safe_data)
            return result.inserted_primary_key[0]

    def update_psu_option(self, psu_id: int, updates: dict) -> bool:
        """更新PSU选项"""
        allowed = {"wattage", "pn", "part_name", "description", "unit_price", "applicable_chassis", "note", "sort_order"}
        fields = []
        values = {}
        for key, val in updates.items():
            if key in allowed:
                if key == "applicable_chassis" and isinstance(val, list):
                    val = json.dumps(val)
                fields.append(f"{key} = :{key}")
                values[key] = val
        if not fields:
            return False
        values["pid"] = psu_id
        q = f"UPDATE l6.l6_psu_options SET {', '.join(fields)} WHERE psu_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), values)
        return True

    def delete_psu_option(self, psu_id: int) -> bool:
        """删除PSU选项"""
        q = "DELETE FROM l6.l6_psu_options WHERE psu_id = :pid"
        with l6_engine.begin() as conn:
            conn.execute(text(q), {"pid": psu_id})
        return True

    def close(self):
        pass
